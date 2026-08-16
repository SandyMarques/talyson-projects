from fastapi import APIRouter, Depends
from app.core.config import settings
from app.schemas.health import HealthResponse
from app.services.vector_store import VectorStoreManager

from app.api.v1.endpoints.documents import get_vector_store

router = APIRouter()


def get_vector_store_manager() -> VectorStoreManager:
    return get_vector_store()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Verificação de integridade da API e do Vector Store",
)
def health_check(
    vector_store: VectorStoreManager = Depends(get_vector_store_manager),
) -> HealthResponse:
    """Verifica se a API está operacional e se o ChromaDB está acessível."""
    is_chroma_ok = vector_store.health_check()
    total_chunks = vector_store.get_total_chunks() if is_chroma_ok else 0

    return HealthResponse(
        status="ok" if is_chroma_ok else "degraded",
        version=settings.API_VERSION,
        vector_store_status="connected" if is_chroma_ok else "disconnected",
        total_indexed_chunks=total_chunks,
    )
