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

    def is_api_key_valid(self, key_to_check: Optional[str] = None) -> bool:
        """Verifica se uma chave de API foi fornecida."""
        key = key_to_check if key_to_check is not None else self.api_key
        return bool(key and isinstance(key, str) and len(key.strip()) > 5)


config = AppConfig()
