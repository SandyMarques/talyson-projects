"""Configurações da aplicação e integração com a DeepSeek."""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    """Configurações centrais do sistema."""
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    default_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    available_models: List[str] = field(default_factory=lambda: ["deepseek-chat", "deepseek-reasoner"])
    max_retries: int = 2
    temperature: float = 0.1
    sample_rows_for_schema: int = 5
    #: Tempo máximo de espera da API. Sem isso o SDK assume 600s e a interface trava sem aviso.
    timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60"))
    )
    #: Teto de tokens de saída: evita resposta que divaga e custo imprevisível.
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("DEEPSEEK_MAX_TOKENS", "2048"))
    )
    #: Limite de caracteres do esquema enviado ao LLM por chamada (orçamento de contexto).
    max_prompt_chars: int = field(
        default_factory=lambda: int(os.getenv("MAX_PROMPT_CHARS", "24000"))
    )
    #: Máximo de linhas aceitas no upload (proteção de memória do processo).
    max_upload_rows: int = field(
        default_factory=lambda: int(os.getenv("MAX_UPLOAD_ROWS", "200000"))
    )
    #: Máximo de colunas aceitas no upload.
    max_upload_columns: int = field(
        default_factory=lambda: int(os.getenv("MAX_UPLOAD_COLUMNS", "500"))
    )

    def is_api_key_valid(self, key_to_check: Optional[str] = None) -> bool:
        """Verifica se uma chave de API foi fornecida."""
        key = key_to_check if key_to_check is not None else self.api_key
        return bool(key and isinstance(key, str) and len(key.strip()) > 5)


config = AppConfig()
