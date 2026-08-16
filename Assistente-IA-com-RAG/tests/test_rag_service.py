import pytest
try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document
from app.schemas.chat import ChatMessage, ChatRequest
from app.services.rag_service import RAGService
from app.services.vector_store import VectorStoreManager


@pytest.mark.asyncio
async def test_rag_service_answer_query(
    rag_service: RAGService, vector_store: VectorStoreManager
):
    # Popula o banco vetorial com um documento
    docs = [
        Document(
            page_content="A capital da França é Paris. Paris é conhecida como a Cidade Luz.",
            metadata={"filename": "geografia.txt", "source": "geografia.txt", "chunk_id": 0, "page": 1},
        ),
    ]
    vector_store.add_documents(docs)

    request = ChatRequest(
        query="Qual é a capital da França?",
        history=[
            ChatMessage(role="user", content="Olá!"),
            ChatMessage(role="assistant", content="Olá! Como posso ajudar?"),
        ],
        top_k=2,
    )

    response = await rag_service.answer_query(request)

    assert response.answer is not None
    assert len(response.answer) > 0
    assert response.sources_count >= 1
    assert len(response.sources) >= 1
    assert response.sources[0].source == "geografia.txt"
    assert response.execution_time_ms >= 0
    assert response.model_used is not None


@pytest.mark.asyncio
async def test_rag_service_no_documents_empty_context(rag_service: RAGService):
    request = ChatRequest(
        query="O que diz o documento?",
        history=[],
    )

    response = await rag_service.answer_query(request)
    assert response.answer is not None
    assert response.sources_count == 0
