"""Endpoint de verificação de integridade.

Decisão de projeto: o health check NÃO exige a chave de API. Ele é o que um balanceador de carga
ou o usuário usa para saber se o serviço está de pé, e não expõe dado algum além de versão e
contagem de chunks. Autenticá-lo quebraria monitores e o próprio painel antes de o usuário
informar a chave.
"""

from fastapi import APIRouter, Depends

from app.api.v1.endpoints.documents import get_vector_store
from app.core.config import settings
from app.schemas.health import HealthResponse
from app.services.vector_store import VectorStoreManager

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Verificação de integridade da API e do Vector Store",
)
def health_check(
    vector_store: VectorStoreManager = Depends(get_vector_store),
) -> HealthResponse:
    """Verifica se a API está operacional e se o ChromaDB está acessível."""
    chroma_ok = vector_store.health_check()
    total_chunks = vector_store.get_total_chunks() if chroma_ok else 0

    return HealthResponse(
        status="ok" if chroma_ok else "degraded",
        version=settings.API_VERSION,
        vector_store_status="connected" if chroma_ok else "disconnected",
        total_indexed_chunks=total_chunks,
    )
