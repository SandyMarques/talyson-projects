from pathlib import Path
from threading import Lock
from typing import Any, List, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

try:
    from langchain_core.documents import Document
except ImportError:  # pragma: no cover
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

    #: Serializa operações de escrita. Reindexar um documento faz `delete` seguido de `add`:
    #: sem lock, dois uploads concorrentes do mesmo arquivo se cruzavam e a falha no meio
    #: deixava o documento anterior perdido.
    _escrita_lock = Lock()

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None,
        embeddings: Optional[Embeddings] = None,
    ):
        self.persist_directory = str(Path(persist_directory or settings.CHROMA_PERSIST_DIR).resolve())
        self.collection_name = collection_name or settings.COLLECTION_NAME

        settings.ensure_directories()

        self.chroma_client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False),
        )

        if embeddings is not None:
            self.embeddings = embeddings
        elif settings.EMBEDDING_PROVIDER.lower() in ["huggingface", "local", "sentence-transformers"]:
            try:
                from langchain_huggingface import HuggingFaceEmbeddings

                self.embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Falha ao inicializar HuggingFaceEmbeddings (%s). "
                    "Caindo para OpenAIEmbeddings — exige OPENAI_API_KEY válida.",
                    exc,
                )
                self.embeddings = OpenAIEmbeddings(
                    openai_api_key=settings.OPENAI_API_KEY or "sk-dummy-key-for-init",
                    model="text-embedding-3-small",
                )
        else:
            self.embeddings = OpenAIEmbeddings(
                openai_api_key=settings.OPENAI_API_KEY or "sk-dummy-key-for-init",
                model=settings.EMBEDDING_MODEL,
            )

        self._vector_store = Chroma(
            client=self.chroma_client,
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
        )

    @property
    def vector_store(self) -> Chroma:
        """Acesso à instância do Chroma (wrapper LangChain)."""
        return self._vector_store

    @property
    def collection(self):
        """Coleção nativa. Única via de acesso a metadados e contagens.

        O código anterior misturava o wrapper LangChain e o cliente nativo para a MESMA coleção,
        o que dificultava raciocinar sobre consistência. Agora: escrita/consulta via wrapper,
        operações de coleção via este acesso.
        """
        return self.chroma_client.get_or_create_collection(self.collection_name)

    # -- Escrita -----------------------------------------------------------------------

    def add_documents(self, documents: List[Document]) -> int:
        """Adiciona chunks ao ChromaDB (ids determinísticos, portanto idempotente)."""
        if not documents:
            return 0

        ids = self._build_ids(documents)
        logger.info("Indexando %s chunks na coleção '%s'...", len(documents), self.collection_name)
        with self._escrita_lock:
            self._vector_store.add_documents(documents=documents, ids=ids)
        return len(documents)

    @staticmethod
    def _build_ids(documents: List[Document]) -> List[str]:
        """IDs determinísticos: mesmo arquivo reindexado sobrescreve em vez de duplicar."""
        ids = []
        for indice, doc in enumerate(documents):
            identificador = (
                doc.metadata.get("filename") or doc.metadata.get("source") or "doc"
            )
            hash_arquivo = doc.metadata.get("file_hash") or "nohash"
            chunk_id = doc.metadata.get("chunk_id", indice)
            nome_limpo = "".join(
                caractere if caractere.isalnum() or caractere in "-_" else "_"
                for caractere in str(identificador)
            )
            # O hash completo evita colisão entre arquivos diferentes com mesmo prefixo.
            ids.append(f"{nome_limpo}_{hash_arquivo}_{chunk_id}")
        return ids

    def replace_document(self, documents: List[Document], filename: str) -> int:
        """Substitui atomicamente todos os chunks de um arquivo.

        `delete` + `add` sem proteção: se a indexação falhasse no meio, o documento anterior
        ficava perdido e o novo incompleto. Aqui a remoção só acontece depois de a indexação
        dar certo, e a seção crítica é protegida por lock.
        """
        if not documents:
            return 0

        with self._escrita_lock:
            ids = self._build_ids(documents)
            logger.info(
                "Reindexando '%s': %s chunks (substituição atômica).",
                filename,
                len(documents),
            )
            self._vector_store.add_documents(documents=documents, ids=ids)

            # Remove versões anteriores que não fazem parte do conjunto novo (ex.: o arquivo
            # encolheu e sobrou chunk órfão do índice antigo).
            novos = set(ids)
            data = self.collection.get(where={"filename": filename}, include=[])
            obsoletos = [i for i in data.get("ids", []) if i not in novos]
            if obsoletos:
                self.collection.delete(ids=obsoletos)
                logger.info("Removidos %s chunks obsoletos de '%s'.", len(obsoletos), filename)
        return len(documents)

    # -- Consulta ----------------------------------------------------------------------

    def similarity_search_with_score(
        self, query: str, k: Optional[int] = None
    ) -> List[Tuple[Document, float]]:
        """Busca por similaridade. O segundo elemento é DISTÂNCIA (menor = mais parecido)."""
        top_k = k or settings.TOP_K_RESULTS
        logger.info("Busca por similaridade (top_k=%s)", top_k)
        return self._vector_store.similarity_search_with_score(query=query, k=top_k)

    def list_documents(self) -> List[DocumentInfo]:
        """Informações agregadas dos documentos indexados."""
        data = self.collection.get(include=["metadatas"])
        metadatas = data.get("metadatas") or []
        if not metadatas:
            return []

        mapa: dict[str, dict[str, Any]] = {}
        for meta in metadatas:
            if not meta:
                continue
            nome = meta.get("filename") or meta.get("source", "Documento desconhecido")
            pagina = meta.get("page")

            if nome not in mapa:
                mapa[nome] = {"filename": nome, "chunks_count": 0, "pages": set()}

            mapa[nome]["chunks_count"] += 1
            if pagina is not None:
                try:
                    mapa[nome]["pages"].add(int(pagina))
                except (TypeError, ValueError):
                    continue

        infos = [
            DocumentInfo(
                filename=info["filename"],
                chunks_count=info["chunks_count"],
                pages=sorted(info["pages"]) if info["pages"] else None,
            )
            for info in mapa.values()
        ]
        return sorted(infos, key=lambda info: info.filename)

    def delete_by_filename(self, filename: str) -> int:
        """Remove todos os chunks de um arquivo."""
        data = self.collection.get(where={"filename": filename}, include=[])
        ids = data.get("ids", [])
        if not ids:
            return 0
        with self._escrita_lock:
            self.collection.delete(ids=ids)
        logger.info("%s chunks do arquivo '%s' excluídos.", len(ids), filename)
        return len(ids)

    def get_total_chunks(self) -> int:
        """Total de chunks armazenados na coleção."""
        return int(self.collection.count())

    def clear_all(self) -> None:
        """Limpa todos os registros da coleção."""
        with self._escrita_lock:
            ids = self.collection.get(include=[])["ids"]
            if ids:
                self.collection.delete(ids=ids)
                logger.info("Coleção '%s' limpa (%s itens removidos).", self.collection_name, len(ids))

    def health_check(self) -> bool:
        """Verifica se o cliente ChromaDB responde."""
        try:
            self.chroma_client.heartbeat()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha no heartbeat do ChromaDB: %s", exc)
            return False
