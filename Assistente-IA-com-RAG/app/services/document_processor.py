import hashlib
import io
from pathlib import Path
from typing import List, Tuple
import pypdf
try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DocumentProcessor:
    """Responsável por carregar arquivos (PDF, TXT, MD), extrair texto e dividi-los em chunks."""

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""],
        )

    @staticmethod
    def calculate_hash(file_bytes: bytes) -> str:
        """Calcula o hash SHA-256 dos bytes do arquivo para controle de integridade."""
        return hashlib.sha256(file_bytes).hexdigest()

    def process_file(
        self, file_bytes: bytes, filename: str
    ) -> Tuple[List[Document], str]:
        """
        Processa os bytes de um arquivo, extrai seu texto e divide em chunks de Document com metadados.
        Retorna a lista de Documents e o hash SHA-256 do arquivo.
        """
        file_ext = Path(filename).suffix.lower()
        file_hash = self.calculate_hash(file_bytes)
        logger.info(f"Processando arquivo: {filename} (Extensão: {file_ext}, Hash: {file_hash[:8]}...)")

        raw_docs: List[Document] = []

        if file_ext == ".pdf":
            raw_docs = self._parse_pdf(file_bytes, filename, file_hash)
        elif file_ext in [".txt", ".md", ".csv", ".json"]:
            raw_docs = self._parse_text(file_bytes, filename, file_hash)
        else:
            # Tenta decodificar como texto puro por padrão
            try:
                raw_docs = self._parse_text(file_bytes, filename, file_hash)
            except Exception as e:
                raise ValueError(
                    f"Formato de arquivo '{file_ext}' não suportado ou ilegível: {str(e)}"
                )

        if not raw_docs:
            raise ValueError(f"O arquivo '{filename}' não contém nenhum texto legível.")

        # Divide os documentos em chunks mantendo os metadados enriquecidos
        split_docs = self.text_splitter.split_documents(raw_docs)

        # Adiciona índice de chunk aos metadados para rastreabilidade
        for idx, doc in enumerate(split_docs):
            doc.metadata["chunk_id"] = idx
            doc.metadata["total_chunks"] = len(split_docs)

        logger.info(
            f"Arquivo '{filename}' processado com sucesso. {len(split_docs)} chunks gerados."
        )
        return split_docs, file_hash

    def _parse_pdf(
        self, file_bytes: bytes, filename: str, file_hash: str
    ) -> List[Document]:
        """Extrai texto página a página de um arquivo PDF usando pypdf."""
        docs: List[Document] = []
        pdf_file = io.BytesIO(file_bytes)
        reader = pypdf.PdfReader(pdf_file)

        for page_idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                docs.append(
                    Document(
                        page_content=text,
                        metadata={
                            "source": filename,
                            "filename": filename,
                            "page": page_idx + 1,
                            "total_pages": len(reader.pages),
                            "file_hash": file_hash,
                        },
                    )
                )

        return docs

    def _parse_text(
        self, file_bytes: bytes, filename: str, file_hash: str
    ) -> List[Document]:
        """Decodifica texto puro (TXT, Markdown, etc.) testando encodings comuns."""
        encodings = ["utf-8", "latin-1", "cp1252"]
        text = None

        for encoding in encodings:
            try:
                text = file_bytes.decode(encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if text is None:
            text = file_bytes.decode("utf-8", errors="replace")

        text = text.strip()
        if not text:
            return []

        return [
            Document(
                page_content=text,
                metadata={
                    "source": filename,
                    "filename": filename,
                    "page": 1,
                    "total_pages": 1,
                    "file_hash": file_hash,
                },
            )
        ]
