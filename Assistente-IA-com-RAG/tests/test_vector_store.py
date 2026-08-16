try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document
from app.services.vector_store import VectorStoreManager


def test_vector_store_add_and_list(vector_store: VectorStoreManager):
    docs = [
        Document(
            page_content="Texto de teste sobre inteligência artificial e aprendizado de máquina.",
            metadata={"filename": "ia.txt", "source": "ia.txt", "chunk_id": 0, "file_hash": "abc1"},
        ),
        Document(
            page_content="Continuação do texto sobre redes neurais e transformadores.",
            metadata={"filename": "ia.txt", "source": "ia.txt", "chunk_id": 1, "file_hash": "abc1"},
        ),
        Document(
            page_content="Guia de instalação do Docker e comandos docker-compose.",
            metadata={"filename": "docker.md", "source": "docker.md", "chunk_id": 0, "file_hash": "xyz2"},
        ),
    ]

    added = vector_store.add_documents(docs)
    assert added == 3
    assert vector_store.get_total_chunks() == 3

    # Lista documentos
    doc_list = vector_store.list_documents()
    assert len(doc_list) == 2
    
    filenames = [d.filename for d in doc_list]
    assert "ia.txt" in filenames
    assert "docker.md" in filenames

    # Valida contagem de chunks por arquivo
    ia_doc = next(d for d in doc_list if d.filename == "ia.txt")
    assert ia_doc.chunks_count == 2


def test_vector_store_similarity_search(vector_store: VectorStoreManager):
    docs = [
        Document(
            page_content="Receita de bolo de chocolate com cobertura de brigadeiro.",
            metadata={"filename": "receitas.txt", "source": "receitas.txt", "chunk_id": 0},
        ),
        Document(
            page_content="Configurando FastAPI com rotas assíncronas e middlewares.",
            metadata={"filename": "fastapi.txt", "source": "fastapi.txt", "chunk_id": 0},
        ),
    ]
    vector_store.add_documents(docs)

    results = vector_store.similarity_search_with_score("Como fazer bolo de chocolate?", k=1)
    assert len(results) == 1
    doc, score = results[0]
    assert doc.metadata["filename"] == "receitas.txt"


def test_vector_store_delete_by_filename(vector_store: VectorStoreManager):
    docs = [
        Document(
            page_content="Documento temporário que será excluído em seguida.",
            metadata={"filename": "temp.txt", "source": "temp.txt", "chunk_id": 0},
        ),
        Document(
            page_content="Documento permanente que deve continuar no banco.",
            metadata={"filename": "perm.txt", "source": "perm.txt", "chunk_id": 0},
        ),
    ]
    vector_store.add_documents(docs)
    assert vector_store.get_total_chunks() == 2

    # Remove o temporário
    deleted = vector_store.delete_by_filename("temp.txt")
    assert deleted == 1
    assert vector_store.get_total_chunks() == 1

    doc_list = vector_store.list_documents()
    assert len(doc_list) == 1
    assert doc_list[0].filename == "perm.txt"


def test_vector_store_clear_all(vector_store: VectorStoreManager):
    docs = [
        Document(
            page_content="Item 1",
            metadata={"filename": "doc1.txt", "source": "doc1.txt", "chunk_id": 0},
        ),
    ]
    vector_store.add_documents(docs)
    assert vector_store.get_total_chunks() == 1

    vector_store.clear_all()
    assert vector_store.get_total_chunks() == 0


def test_vector_store_health_check(vector_store: VectorStoreManager):
    assert vector_store.health_check() is True
