from pathlib import Path
from typing import List

from pydantic import Field, field_validator
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

    #: Origens permitidas por CORS. Default restrito a desenvolvimento local — NUNCA `*`.
    #: Como este serviço não usa cookies nem credenciais, `allow_credentials` fica desligado.
    #: Aceita JSON (`["https://app.exemplo"]`) ou lista separada por vírgulas.
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:8000", "http://127.0.0.1:8000"]
    )

    #: Liga/desliga a exigência de chave de API nos endpoints. Em produção, mantenha ligado.
    REQUIRE_API_KEY: bool = True
    #: Chave esperada no header `X-API-Key`. Vazio desabilita a checagem (apenas com
    #: REQUIRE_API_KEY=False, para uso local).
    API_KEY: str = ""

    #: Expor /docs, /redoc e /openapi.json. Fora de desenvolvimento isso deve ficar desligado.
    EXPOSE_DOCS: bool = False

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

    #: Timeout (segundos) das chamadas ao provedor de LLM.
    LLM_TIMEOUT_SECONDS: float = Field(default=60.0, description="Timeout das chamadas ao LLM")
    #: Máximo de tokens da resposta gerada.
    LLM_MAX_TOKENS: int = Field(default=1500, description="Teto de tokens da resposta")

    # ChromaDB & Armazenamento
    CHROMA_PERSIST_DIR: str = Field(default="./data/chroma", description="Diretório de persistência do ChromaDB")
    COLLECTION_NAME: str = Field(default="rag_documents", description="Nome da coleção no ChromaDB")
    UPLOAD_DIR: str = Field(default="./data/uploads", description="Diretório para arquivos enviados")

    # Parâmetros de RAG e Chunking
    CHUNK_SIZE: int = Field(default=1000, description="Tamanho de cada chunk de texto")
    CHUNK_OVERLAP: int = Field(default=200, description="Sobreposição entre chunks consecutivos")
    TOP_K_RESULTS: int = Field(default=4, description="Quantidade de chunks mais relevantes a recuperar")
    #: Distância máxima aceita na recuperação (L2 ao quadrado do Chroma). Trechos acima disso
    #: são descartados em vez de aparecerem como "fonte citada".
    MIN_RELEVANCE_DISTANCE: float = Field(
        default=1.5, description="Distância máxima aceita para um trecho ser usado como contexto"
    )

    #: Limite de upload em bytes (padrão 25 MB). Sem isso o arquivo é lido inteiro na memória.
    MAX_UPLOAD_BYTES: int = Field(default=25 * 1024 * 1024, description="Tamanho máximo de upload")

    #: Orçamento de contexto: número máximo de caracteres de contexto enviados ao LLM.
    MAX_CONTEXT_CHARS: int = Field(
        default=12000, description="Teto de caracteres do contexto montado a partir dos documentos"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, valor):
        """Aceita lista, JSON ou string separada por vírgulas.

        Antes, definir `CORS_ORIGINS=*` no ambiente derrubava o startup com SettingsError
        (`CORS_ORIGINS` é `List[str]` e o pydantic-settings não convertia a string crua).
        """
        if valor is None or valor == "":
            return ["http://localhost:8000", "http://127.0.0.1:8000"]
        if isinstance(valor, str):
            texto = valor.strip()
            if texto.startswith("["):
                import json

                try:
                    convertido = json.loads(texto)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "CORS_ORIGINS em formato JSON inválido. Use "
                        '\'["https://app.exemplo"]\' ou "https://a.com,https://b.com".'
                    ) from exc
                if not isinstance(convertido, list):
                    raise ValueError("CORS_ORIGINS em JSON deve ser uma lista de origens.")
                return [str(item).strip() for item in convertido if str(item).strip()]
            return [parte.strip() for parte in texto.split(",") if parte.strip()]
        if isinstance(valor, (list, tuple)):
            return [str(item).strip() for item in valor if str(item).strip()]
        return valor

    @field_validator("LLM_PROVIDER")
    @classmethod
    def _validar_provedor(cls, valor: str) -> str:
        normalizado = valor.strip().lower()
        if normalizado not in {"deepseek", "openai"}:
            raise ValueError("LLM_PROVIDER deve ser 'deepseek' ou 'openai'.")
        return normalizado

    def ensure_directories(self) -> None:
        """Garante que os diretórios necessários para armazenamento existam."""
        Path(self.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    def llm_api_key_configured(self) -> bool:
        """Indica se a chave do provedor ativo está realmente preenchida.

        Existe para que a validação não dependa de um atributo interno do cliente LLM
        (a versão anterior usava `hasattr(llm, "response_text")`, que só existe no mock de
        teste — ou seja, a checagem de produção estava acoplada ao fixture).
        """
        chave = (
            self.DEEPSEEK_API_KEY
            if self.LLM_PROVIDER == "deepseek"
            else self.OPENAI_API_KEY
        )
        return bool(chave and chave.strip() and "dummy" not in chave and "sua_chave" not in chave)


settings = Settings()
