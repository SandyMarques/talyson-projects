from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.endpoints.documents import get_vector_store
from app.core.logging import get_logger
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import RAGService

logger = get_logger(__name__)
router = APIRouter()


def get_rag_service() -> RAGService:
    return RAGService(vector_store_manager=get_vector_store())


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
    """
    Recebe a pergunta do usuário e o histórico de mensagens, consulta os chunks
    mais relevantes no ChromaDB e gera a resposta contextualizada com referências de fontes.
    """
    if not request.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A pergunta não pode estar vazia.",
        )

    try:
        response = await rag_service.answer_query(request)
        return response
    except Exception as e:
        logger.error(f"Erro ao processar consulta RAG: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao gerar resposta com RAG: {str(e)}",
        )
