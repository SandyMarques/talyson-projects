"""Fixtures compartilhadas da suíte de testes.

Princípios aplicados:
- **Isolamento real** (causa nº 1 de flaky tests, Fowler): cada teste que toca o vector store
  recebe um diretório temporário próprio; nada de estado compartilhado entre testes.
- **Sem serviços remotos** (causa nº 3): embeddings determinísticos e LLM fake, então a suíte
  roda 100% offline e em milissegundos.
- **Sem dependência de relógio** (causa nº 4): as asserções não dependem de tempo.
- **Test doubles conscientes**: `MockDeterministicEmbeddings` é um **Fake** (implementação
  funcional simplificada), `MockChatModel` é um **Stub** (resposta pré-determinada). Não usamos
  Mock estrito para o LLM no nível do serviço, para não acoplar o teste ao fluxo interno.
"""

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
from app.core.config import Settings, settings
from app.main import app
from app.services.document_processor import DocumentProcessor
from app.services.rag_service import RAGService
from app.services.vector_store import VectorStoreManager


class MockDeterministicEmbeddings(Embeddings):
    """Fake de embeddings: determinístico, offline e sensível à sobreposição de palavras."""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_embedding(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._generate_embedding(text)

    def _generate_embedding(self, text: str) -> List[float]:
        """Vetor normalizado de frequência de palavras (bag-of-words determinístico)."""
        vec = [0.0] * self.dimension
        for palavra in text.lower().split():
            indice = sum(ord(c) for c in palavra) % self.dimension
            vec[indice] += 1.0

        if sum(vec) == 0:
            for indice, caractere in enumerate(text[: self.dimension]):
                vec[indice % self.dimension] += ord(caractere) / 100.0

        norma = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norma for x in vec]


class MockChatModel(BaseChatModel):
    """Stub de LLM: resposta fixa, sem chamada de rede."""

    response_text: str = "Esta é uma resposta simulada baseada estritamente no documento de teste."

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.response_text))]
        )

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


@pytest.fixture(autouse=True)
def _credenciais_de_teste(monkeypatch):
    """Faz a validação de chave passar por padrão, com LLM stub.

    O serviço valida a chave do provedor contra o `.env` (correto em produção, e antes essa
    checagem estava acoplada a um atributo do mock). Nos testes o LLM é um stub, então a chave
    é irrelevante: aqui a checagem é neutralizada explicitamente. O teste que verifica o
    comportamento SEM chave reativa isso com `monkeypatch`.
    """
    monkeypatch.setattr(Settings, "llm_api_key_configured", lambda self: True)


@pytest.fixture
def temp_chroma_dir():
    """Diretório temporário isolado para o ChromaDB (limpo ao final)."""
    temp_dir = tempfile.mkdtemp(prefix="chroma_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_embeddings():
    """Fake de embeddings determinístico."""
    return MockDeterministicEmbeddings(dimension=64)


@pytest.fixture
def mock_chat_model():
    """Stub de LLM."""
    return MockChatModel()


@pytest.fixture
def document_processor():
    """Processador com chunks pequenos, para exercitar a divisão de verdade."""
    return DocumentProcessor(chunk_size=100, chunk_overlap=20)


@pytest.fixture
def vector_store(temp_chroma_dir, mock_embeddings) -> VectorStoreManager:
    """Instância isolada do VectorStoreManager, com embeddings fake."""
    return VectorStoreManager(
        persist_directory=temp_chroma_dir,
        collection_name="test_collection",
        embeddings=mock_embeddings,
    )


@pytest.fixture
def rag_service(vector_store, mock_chat_model) -> RAGService:
    """RAGService com store isolado e LLM stub."""
    return RAGService(vector_store_manager=vector_store, llm=mock_chat_model)


@pytest.fixture
def client(vector_store, rag_service) -> TestClient:
    """Cliente HTTP com as dependências trocadas por fakes.

    A autenticação é desligada explicitamente nesta fixture: os testes de autenticação vivem em
    `test_security_api.py`, onde ela é ligada de propósito. Assim cada teste declara a política
    que está exercitando em vez de depender do default do ambiente.
    """
    app.dependency_overrides[get_vector_store] = lambda: vector_store
    app.dependency_overrides[get_rag_service] = lambda: rag_service

    api_key_anterior = settings.API_KEY
    require_anterior = settings.REQUIRE_API_KEY
    settings.REQUIRE_API_KEY = False
    settings.API_KEY = ""

    with TestClient(app) as test_client:
        yield test_client

    settings.API_KEY = api_key_anterior
    settings.REQUIRE_API_KEY = require_anterior
    app.dependency_overrides.clear()
