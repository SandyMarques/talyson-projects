from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação carregadas de variáveis de ambiente ou arquivo .env."""

    # Informações da API
    API_TITLE: str = "Assistente IA com RAG"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = (
        "API para chat inteligente com RAG (Retrieval-Augmented Generation) "
        "integrando FastAPI, LangChain, ChromaDB e OpenAI."
    )
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = ["*"]

    # Provedores de LLM & IA
    LLM_PROVIDER: str = Field(default="deepseek", description="Provedor de LLM padrão: deepseek ou openai")
    
    # DeepSeek
    DEEPSEEK_API_KEY: str = Field(default="", description="Chave de API da DeepSeek")
    DEEPSEEK_MODEL: str = Field(default="deepseek-chat", description="Modelo DeepSeek padrão (ex: deepseek-chat, deepseek-reasoner)")
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com", description="Base URL da API DeepSeek")

    # OpenAI (Opcional / Fallback)
    OPENAI_API_KEY: str = Field(default="", description="Chave de API da OpenAI (opcional)")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="Modelo LLM alternativo OpenAI")

    # Embeddings
    EMBEDDING_PROVIDER: str = Field(
        default="huggingface", 
        description="Provedor de embeddings: 'huggingface' (local/gratuito) ou 'openai'"
    )
    EMBEDDING_MODEL: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", 
        description="Modelo de embeddings (ex: sentence-transformers/all-MiniLM-L6-v2 para local, ou text-embedding-3-small para OpenAI)"
    )
    TEMPERATURE: float = Field(default=0.0, description="Temperatura do modelo para respostas precisas")

    # ChromaDB & Armazenamento
    CHROMA_PERSIST_DIR: str = Field(default="./data/chroma", description="Diretório de persistência do ChromaDB")
    COLLECTION_NAME: str = Field(default="rag_documents", description="Nome da coleção no ChromaDB")
    UPLOAD_DIR: str = Field(default="./data/uploads", description="Diretório para arquivos enviados")

    # Parâmetros de RAG e Chunking
    CHUNK_SIZE: int = Field(default=1000, description="Tamanho de cada chunk de texto")
    CHUNK_OVERLAP: int = Field(default=200, description="Sobreposição entre chunks consecutivos")
    TOP_K_RESULTS: int = Field(default=4, description="Quantidade de chunks mais relevantes a recuperar")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_directories(self) -> None:
        """Garante que os diretórios necessários para armazenamento existam."""
        Path(self.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


settings = Settings()
