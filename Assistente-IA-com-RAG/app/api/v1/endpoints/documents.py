from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.logging import get_logger
from app.schemas.document import (
    DocumentInfo,
    DocumentListResponse,
    DocumentUploadResponse,
)
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import VectorStoreManager

from functools import lru_cache

logger = get_logger(__name__)
router = APIRouter()


@lru_cache(maxsize=1)
def get_doc_processor() -> DocumentProcessor:
    return DocumentProcessor()


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStoreManager:
    return VectorStoreManager()


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload e processamento de documento (PDF, TXT, MD)",
)
async def upload_document(
    file: UploadFile = File(...),
    processor: DocumentProcessor = Depends(get_doc_processor),
    vector_store: VectorStoreManager = Depends(get_vector_store),
) -> DocumentUploadResponse:
    """
    Recebe um arquivo (PDF, TXT ou MD), processa seu conteúdo em chunks com metadados
    e indexa as representações vetoriais no ChromaDB.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum arquivo enviado ou nome de arquivo inválido.",
        )

    filename = file.filename
    file_ext = Path(filename).suffix.lower()

    if file_ext not in [".pdf", ".txt", ".md", ".csv", ".json"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extensão '{file_ext}' não suportada. Envie arquivos PDF, TXT, MD, CSV ou JSON.",
        )

    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O arquivo enviado está vazio.",
            )

        # Processa e divide em chunks
        chunks, doc_hash = processor.process_file(file_bytes, filename)

        # Remove versão anterior do mesmo arquivo se já existir (para evitar duplicatas)
        vector_store.delete_by_filename(filename)

        # Indexa os novos chunks no ChromaDB
        indexed_count = vector_store.add_documents(chunks)

        return DocumentUploadResponse(
            filename=filename,
            file_type=file_ext.replace(".", ""),
            total_chunks=indexed_count,
            document_hash=doc_hash,
            message=f"Documento '{filename}' processado e indexado com sucesso ({indexed_count} chunks gerados).",
        )

    except ValueError as ve:
        logger.warning(f"Erro de validação ao processar documento: {ve}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(f"Erro inesperado ao processar upload: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha interna ao processar documento: {str(e)}",
        )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="Listar todos os documentos indexados no vector store",
)
def list_documents(
    vector_store: VectorStoreManager = Depends(get_vector_store),
) -> DocumentListResponse:
    """Retorna a lista de todos os documentos atualmente presentes na base vetorial."""
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
    """Exclui todos os chunks associados a um arquivo específico da base vetorial."""
    deleted_count = vector_store.delete_by_filename(filename)
    if deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento '{filename}' não encontrado no banco vetorial.",
        )

    return {
        "message": f"Documento '{filename}' e seus {deleted_count} chunks foram removidos com sucesso.",
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
    """Remove completamente todos os documentos e chunks da base vetorial."""
    total_chunks = vector_store.get_total_chunks()
    vector_store.clear_all()
    return {
        "message": f"Base vetorial limpa com sucesso ({total_chunks} chunks removidos).",
        "deleted_chunks": total_chunks,
    }
