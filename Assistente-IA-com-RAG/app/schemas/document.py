from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """Resposta após upload e processamento de documento."""
    filename: str = Field(..., description="Nome do arquivo processado")
    file_type: str = Field(..., description="Tipo do arquivo (pdf, txt, md)")
    total_chunks: int = Field(..., description="Quantidade de chunks gerados e indexados")
    document_hash: str = Field(..., description="Hash SHA-256 do arquivo para controle de integridade")
    message: str = Field(..., description="Mensagem informativa sobre a ingestão")


class DocumentInfo(BaseModel):
    """Informações sobre um documento indexado no ChromaDB."""
    filename: str = Field(..., description="Nome do arquivo")
    chunks_count: int = Field(..., description="Quantidade de chunks indexados para este documento")
    pages: Optional[List[int]] = Field(default=None, description="Lista de páginas encontradas")


class DocumentListResponse(BaseModel):
    """Lista de todos os documentos presentes no vector store."""
    total_documents: int = Field(..., description="Total de documentos distintos")
    total_chunks: int = Field(..., description="Total de chunks vetoriais armazenados")
    documents: List[DocumentInfo] = Field(default=[], description="Detalhes de cada documento")
