import os
import shutil
import tempfile
from typing import Any, List, Optional
import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.api.v1.endpoints.chat import get_rag_service
from app.api.v1.endpoints.documents import get_vector_store
from app.api.v1.endpoints.health import get_vector_store_manager
from app.core.config import settings
from app.main import app
from app.services.document_processor import DocumentProcessor
from app.services.rag_service import RAGService
from app.services.vector_store import VectorStoreManager


class MockDeterministicEmbeddings(Embeddings):
    """Embeddings determinísticos para testes sem chamada à API externa."""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_embedding(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._generate_embedding(text)

    def _generate_embedding(self, text: str) -> List[float]:
        # Gera vetor determinístico usando frequência e hash de palavras
        vec = [0.0] * self.dimension
        words = text.lower().split()
        for word in words:
            idx = sum(ord(c) for c in word) % self.dimension
            vec[idx] += 1.0

        if sum(vec) == 0:
            for i, c in enumerate(text[:self.dimension]):
                vec[i % self.dimension] += ord(c) / 100.0

        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]


class MockChatModel(BaseChatModel):
    """Modelo de chat simulado para testes rápidos e previsíveis."""

    response_text: str = "Esta é uma resposta simulada baseada estritamente no documento de teste."

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = AIMessage(content=self.response_text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "mock-chat-model"


@pytest.fixture
def temp_chroma_dir():
    """Cria um diretório temporário isolado para persistência do ChromaDB em testes."""
    temp_dir = tempfile.mkdtemp(prefix="chroma_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_embeddings():
    """Instância de embeddings determinísticos."""
    return MockDeterministicEmbeddings(dimension=64)


@pytest.fixture
def mock_chat_model():
    """Instância de LLM simulada."""
    return MockChatModel()


@pytest.fixture
def document_processor():
    """Instância do DocumentProcessor com chunks pequenos para testes."""
    return DocumentProcessor(chunk_size=100, chunk_overlap=20)


@pytest.fixture
def vector_store(temp_chroma_dir, mock_embeddings):
    """Instância isolada de VectorStoreManager usando diretório temporário e mock de embeddings."""
    return VectorStoreManager(
        persist_directory=temp_chroma_dir,
        collection_name="test_collection",
        embeddings=mock_embeddings,
    )


@pytest.fixture
def rag_service(vector_store, mock_chat_model):
    """Instância do RAGService com vector store e LLM simulados."""
    return RAGService(vector_store_manager=vector_store, llm=mock_chat_model)


@pytest.fixture
def client(vector_store, rag_service):
    """Cliente de teste FastAPI com dependências injetadas."""
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_vector_store_manager] = lambda: vector_store
    app.dependency_overrides[get_rag_service] = lambda: rag_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
