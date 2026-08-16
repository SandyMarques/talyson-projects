from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Schema para verificação de saúde da aplicação e serviços."""
    status: str = Field(..., description="Status geral do serviço (ok, degraded, error)")
    version: str = Field(..., description="Versão da API")
    vector_store_status: str = Field(..., description="Status de conexão com o banco vetorial ChromaDB")
    total_indexed_chunks: int = Field(default=0, description="Total de chunks indexados no vector store")
