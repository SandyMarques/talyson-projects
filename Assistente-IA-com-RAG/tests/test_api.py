import io
from fastapi.testclient import TestClient


def test_api_health_endpoint(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "degraded"]
    assert "version" in data
    assert "vector_store_status" in data


def test_api_upload_and_list_document(client: TestClient):
    file_content = "Este é um arquivo de teste de upload para o RAG Assistant."
    file_obj = io.BytesIO(file_content.encode("utf-8"))

    # Upload
    upload_res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("guia_teste.txt", file_obj, "text/plain")},
    )
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    assert upload_data["filename"] == "guia_teste.txt"
    assert upload_data["total_chunks"] >= 1

    # List
    list_res = client.get("/api/v1/documents")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total_documents"] >= 1
    assert any(doc["filename"] == "guia_teste.txt" for doc in list_data["documents"])


def test_api_upload_invalid_extension(client: TestClient):
    file_obj = io.BytesIO(b"conteudo binario")
    res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("invalido.exe", file_obj, "application/octet-stream")},
    )
    assert res.status_code == 400
    assert "não suportada" in res.json()["detail"]


def test_api_chat_endpoint(client: TestClient):
    # Primeiro envia um documento para garantir contexto
    file_content = "O projeto RAG Assistant foi desenvolvido com FastAPI e ChromaDB."
    client.post(
        "/api/v1/documents/upload",
        files={"file": ("projeto.txt", io.BytesIO(file_content.encode("utf-8")), "text/plain")},
    )

    # Realiza pergunta
    chat_res = client.post(
        "/api/v1/chat",
        json={"query": "Quais tecnologias foram usadas no projeto?"},
    )
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert "answer" in data
    assert "sources" in data
    assert "execution_time_ms" in data
    assert data["sources_count"] >= 1


def test_api_chat_empty_query_error(client: TestClient):
    res = client.post("/api/v1/chat", json={"query": "   "})
    assert res.status_code == 400


def test_api_delete_document(client: TestClient):
    # Upload
    client.post(
        "/api/v1/documents/upload",
        files={"file": ("remover.txt", io.BytesIO(b"Documento a ser removido"), "text/plain")},
    )

    # Delete
    del_res = client.delete("/api/v1/documents/remover.txt")
    assert del_res.status_code == 200

    # Delete not found
    del_res2 = client.delete("/api/v1/documents/arquivo_inexistente.txt")
    assert del_res2.status_code == 404
