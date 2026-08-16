from pathlib import Path
from typing import Any, List, Optional, Tuple
import chromadb
from chromadb.config import Settings as ChromaSettings
try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.document import DocumentInfo

logger = get_logger(__name__)


class VectorStoreManager:
    """Gerenciador do banco vetorial ChromaDB e operações de busca por similaridade."""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
        embeddings: Optional[Embeddings] = None,
    ):
        self.persist_directory = str(Path(persist_directory or settings.CHROMA_PERSIST_DIR).resolve())
        self.collection_name = collection_name or settings.COLLECTION_NAME

        # Garante criação do diretório de persistência
        settings.ensure_directories()

        # Configura cliente nativo do ChromaDB
        self.chroma_client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )

        # Configura embeddings padrão se não fornecido
        if embeddings is not None:
            self.embeddings = embeddings
        elif settings.EMBEDDING_PROVIDER.lower() in ["huggingface", "local", "sentence-transformers"]:
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
                self.embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
            except Exception as e:
                logger.warning(f"Erro ao inicializar HuggingFaceEmbeddings ({e}), fallback para OpenAIEmbeddings.")
                self.embeddings = OpenAIEmbeddings(
                    openai_api_key=settings.OPENAI_API_KEY or "sk-dummy-key-for-init",
                    model="text-embedding-3-small",
                )
        else:
            self.embeddings = OpenAIEmbeddings(
                openai_api_key=settings.OPENAI_API_KEY or "sk-dummy-key-for-init",
                model=settings.EMBEDDING_MODEL,
            )

        # Inicializa wrapper LangChain Chroma
        self._vector_store = Chroma(
            client=self.chroma_client,
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
        )

    @property
    def vector_store(self) -> Chroma:
        """Acesso à instância do Chroma."""
        return self._vector_store

    def add_documents(self, documents: List[Document]) -> int:
        """Adiciona lista de documentos em chunks ao ChromaDB."""
        if not documents:
            return 0

        # Constrói IDs únicos e determinísticos para cada chunk
        ids = []
        for idx, doc in enumerate(documents):
            file_identifier = doc.metadata.get("filename") or doc.metadata.get("source") or "doc"
            doc_hash = doc.metadata.get("file_hash") or "nohash"
            chunk_id = doc.metadata.get("chunk_id", idx)
            clean_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in file_identifier)
            ids.append(f"{clean_name}_{doc_hash[:8]}_{chunk_id}_{idx}")

        logger.info(
            f"Indexando {len(documents)} chunks na coleção '{self.collection_name}'..."
        )
        self._vector_store.add_documents(documents=documents, ids=ids)
        return len(documents)

    def similarity_search_with_score(
        self, query: str, k: Optional[int] = None
    ) -> List[Tuple[Document, float]]:
        """Realiza busca por similaridade vetorial com pontuação de distância."""
        top_k = k or settings.TOP_K_RESULTS
        logger.info(f"Executando busca por similaridade para a query: '{query}' (top_k={top_k})")
        results = self._vector_store.similarity_search_with_score(query=query, k=top_k)
        return results

    def list_documents(self) -> List[DocumentInfo]:
        """Recupera informações agregadas sobre todos os documentos indexados."""
        collection = self.chroma_client.get_or_create_collection(self.collection_name)
        data = collection.get(include=["metadatas"])

        metadatas = data.get("metadatas", [])
        if not metadatas:
            return []

        doc_map: dict[str, dict[str, Any]] = {}
        for meta in metadatas:
            if not meta:
                continue
            filename = meta.get("filename") or meta.get("source", "Documento desconhecido")
            page = meta.get("page")

            if filename not in doc_map:
                doc_map[filename] = {
                    "filename": filename,
                    "chunks_count": 0,
                    "pages": set(),
                }

            doc_map[filename]["chunks_count"] += 1
            if page is not None:
                doc_map[filename]["pages"].add(int(page))

        doc_infos = [
            DocumentInfo(
                filename=info["filename"],
                chunks_count=info["chunks_count"],
                pages=sorted(list(info["pages"])) if info["pages"] else None,
            )
            for info in doc_map.values()
        ]
        return sorted(doc_infos, key=lambda d: d.filename)

    def delete_by_filename(self, filename: str) -> int:
        """Remove todos os chunks associados a um arquivo específico."""
        collection = self.chroma_client.get_or_create_collection(self.collection_name)
        data = collection.get(
            where={"filename": filename},
            include=["metadatas"],
        )
        ids_to_delete = data.get("ids", [])
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            logger.info(f"{len(ids_to_delete)} chunks do arquivo '{filename}' foram excluídos.")
            return len(ids_to_delete)
        return 0

    def get_total_chunks(self) -> int:
        """Retorna o número total de chunks armazenados na coleção."""
        collection = self.chroma_client.get_or_create_collection(self.collection_name)
        return collection.count()

    def clear_all(self) -> None:
        """Limpa todos os registros da coleção vetorial."""
        collection = self.chroma_client.get_or_create_collection(self.collection_name)
        all_ids = collection.get()["ids"]
        if all_ids:
            collection.delete(ids=all_ids)
            logger.info(f"Coleção '{self.collection_name}' limpa ({len(all_ids)} itens removidos).")

    def health_check(self) -> bool:
        """Verifica se o cliente ChromaDB está funcional."""
        try:
            self.chroma_client.heartbeat()
            return True
        except Exception as e:
            logger.error(f"Falha no heartbeat do ChromaDB: {e}")
            return False
