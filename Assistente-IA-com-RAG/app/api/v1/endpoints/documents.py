"""Endpoints de documentos: upload, listagem e exclusão.

Correções aplicadas:

1. **Limite de tamanho no upload**: antes era `await file.read()` do arquivo inteiro antes de
   qualquer validação — um arquivo grande derrubava a API. Agora a leitura é em blocos, com corte
   ao exceder `MAX_UPLOAD_BYTES`.
2. **Parsing fora do event loop**: o parse de PDF e o cálculo de embeddings são síncronos e
   bloqueantes; passam por `asyncio.to_thread`.
3. **Reindexação atômica**: `delete` + `add` sem proteção podia perder o documento anterior.
4. **Nome de arquivo saneado**: o nome vem do multipart e é controlado pelo cliente. Ele era
   gravado como metadado e exibido no painel sem escape (XSS armazenado). Agora é normalizado
   aqui e escapado no frontend.
5. **Autenticação** por `X-API-Key` em todas as rotas.
"""

import asyncio
from functools import lru_cache
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import require_api_key
from app.schemas.document import (
    DocumentInfo,
    DocumentListResponse,
    DocumentUploadResponse,
)
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import VectorStoreManager

logger = get_logger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])

EXTENSOES_PERMITIDAS = {".pdf", ".txt", ".md", ".csv", ".json"}


@lru_cache(maxsize=1)
def get_doc_processor() -> DocumentProcessor:
    """Processador único (reutiliza o text splitter entre requisições)."""
    return DocumentProcessor()


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStoreManager:
    """Store único, alinhado ao pipeline de produção.

    O ciclo de vida ideal é criar isso no `lifespan` da aplicação; usar `lru_cache` aqui é uma
    solução intermediária que evita reabrir o cliente Chroma e recarregar o modelo de embeddings
    a cada requisição (era um problema real de latência e memória).
    """
    return VectorStoreManager()


def sanitize_filename(nome_bruto: str) -> str:
    """Normaliza o nome recebido no multipart para um nome de arquivo seguro.

    Descarta caminho (inclusive `..\\` e `/`), caracteres de controle, aspas/`<`/`>` (vetores de
    injeção em HTML e em header) e limita o tamanho.
    """
    if not nome_bruto:
        return ""

    # `Path(...).name` isola o nome base em ambos os dialetos: "..\\..\\etc\\passwd" -> "passwd".
    nome = PureWindowsPath(PurePosixPath(nome_bruto).name).name
    nome = nome.replace("\x00", "")
    permitido = []
    for caractere in nome:
        if caractere.isalnum() or caractere in " ._-()[]":
            permitido.append(caractere)
        else:
            permitido.append("_")
    limpo = "".join(permitido).strip().strip(".")
    limpo = " ".join(limpo.split())
    if len(limpo) > 180:
        sufixo = Path(limpo).suffix
        limpo = limpo[: 180 - len(sufixo)] + sufixo
    return limpo


async def read_upload_limited(file: UploadFile, limite: int) -> bytes:
    """Lê o upload em blocos, abortando ao exceder o limite."""
    blocos: List[bytes] = []
    total = 0
    while True:
        bloco = await file.read(1024 * 1024)
        if not bloco:
            break
        total += len(bloco)
        if total > limite:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"O arquivo excede o limite de {limite // (1024 * 1024)} MB. "
                    "Divida o documento ou aumente MAX_UPLOAD_BYTES."
                ),
            )
        blocos.append(bloco)
    return b"".join(blocos)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload e processamento de documento (PDF, TXT, MD, CSV, JSON)",
)
async def upload_document(
    file: UploadFile = File(...),
    processor: DocumentProcessor = Depends(get_doc_processor),
    vector_store: VectorStoreManager = Depends(get_vector_store),
) -> DocumentUploadResponse:
    """Recebe um arquivo, divide em chunks com metadados e indexa no ChromaDB."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum arquivo enviado ou nome de arquivo inválido.",
        )

    filename = sanitize_filename(file.filename)
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O nome do arquivo não contém caracteres válidos.",
        )

    file_ext = Path(filename).suffix.lower()
    if file_ext not in EXTENSOES_PERMITIDAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Extensão '{file_ext}' não suportada. "
                f"Envie arquivos {', '.join(sorted(e[1:].upper() for e in EXTENSOES_PERMITIDAS))}."
            ),
        )

    file_bytes = await read_upload_limited(file, settings.MAX_UPLOAD_BYTES)
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O arquivo enviado está vazio.",
        )

    try:
        # Parsing de PDF e chunking são síncronos: fora do event loop.
        chunks, doc_hash = await asyncio.to_thread(processor.process_file, file_bytes, filename)

        # Substituição atômica: só remove o documento anterior depois de indexar o novo.
        indexed_count = await asyncio.to_thread(
            vector_store.replace_document, chunks, filename
        )

        return DocumentUploadResponse(
            filename=filename,
            file_type=file_ext.replace(".", ""),
            total_chunks=indexed_count,
            document_hash=doc_hash,
            message=(
                f"Documento '{filename}' processado e indexado com sucesso "
                f"({indexed_count} chunks gerados)."
            ),
        )

    except HTTPException:
        raise
    except ValueError as erro_validacao:
        logger.warning("Erro de validação ao processar documento: %s", erro_validacao)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(erro_validacao),
        ) from erro_validacao
    except Exception as erro:  # noqa: BLE001
        # Detalhe interno não vai para o cliente: evita expor caminhos, URLs e mensagens do SDK.
        logger.error("Erro inesperado ao processar upload: %s", erro, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha interna ao processar o documento. Consulte os logs do servidor.",
        ) from erro


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="Listar todos os documentos indexados no vector store",
)
def list_documents(
    vector_store: VectorStoreManager = Depends(get_vector_store),
) -> DocumentListResponse:
    """Retorna a lista de documentos presentes na base vetorial."""
    docs: List[DocumentInfo] = vector_store.list_documents()
    total_chunks = vector_store.get_total_chunks()

    return DocumentListResponse(
        total_documents=len(docs),
        total_chunks=total_chunks,
        documents=docs,
    )


@router.delete(
    "/{filename}",
    status_code=status.HTTP_200_OK,
    summary="Excluir documento indexado pelo nome do arquivo",
)
def delete_document(
    filename: str,
    vector_store: VectorStoreManager = Depends(get_vector_store),
) -> dict:
    """Exclui todos os chunks de um arquivo específico."""
    deleted_count = vector_store.delete_by_filename(sanitize_filename(filename))
    if deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento '{sanitize_filename(filename)}' não encontrado no banco vetorial.",
        )

    return {
        "message": f"Documento '{filename}' e seus {deleted_count} chunks foram removidos.",
        "filename": filename,
        "deleted_chunks": deleted_count,
    }


@router.delete(
    "",
    status_code=status.HTTP_200_OK,
    summary="Limpar todos os documentos da base vetorial",
)
def clear_all_documents(
    vector_store: VectorStoreManager = Depends(get_vector_store),
) -> dict:
    """Remove todos os documentos e chunks da base vetorial."""
    total_chunks = vector_store.get_total_chunks()
    vector_store.clear_all()
    logger.warning("Base vetorial limpa via API (%s chunks removidos).", total_chunks)
    return {
        "message": f"Base vetorial limpa com sucesso ({total_chunks} chunks removidos).",
        "deleted_chunks": total_chunks,
    }
