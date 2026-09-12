"""Endpoint de chat com RAG.

Correções: autenticação obrigatória, erros internos do provedor não vazam para o cliente, e a
exceção de configuração ausente vira 503 com mensagem acionável (antes era 500 genérico).
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.endpoints.documents import get_vector_store
from app.core.logging import get_logger
from app.core.security import require_api_key
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import LLMNotConfiguredError, RAGService
from app.services.vector_store import VectorStoreManager

logger = get_logger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])


def get_rag_service(
    vector_store: VectorStoreManager = Depends(get_vector_store),
) -> RAGService:
    """Instancia o serviço reutilizando o store já aberto."""
    return RAGService(vector_store_manager=vector_store)


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Realizar pergunta ao assistente RAG com base nos documentos",
)
async def chat_rag(
    request: ChatRequest,
    rag_service: RAGService = Depends(get_rag_service),
) -> ChatResponse:
    """Recebe a pergunta e o histórico, recupera contexto e gera a resposta com fontes."""
    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A pergunta não pode estar vazia.",
        )

    try:
        return await rag_service.answer_query(request)
    except LLMNotConfiguredError as erro_config:
        # Falha de configuração do servidor: 503 com instrução, não 500 genérico.
        logger.error("Provedor de LLM não configurado: %s", erro_config)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(erro_config),
        ) from erro_config
    except Exception as erro:  # noqa: BLE001
        # `str(exc)` do provedor pode conter URL, corpo de resposta e detalhes da chave:
        # fica no log do servidor, não na resposta HTTP.
        logger.error("Erro ao processar consulta RAG: %s", erro, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao gerar a resposta. Consulte os logs do servidor.",
        ) from erro
