"""Cliente DeepSeek utilizando o SDK compatível com OpenAI e suporte a múltiplas abas."""

import re
from typing import Dict, Optional, Tuple, Union
import pandas as pd
from openai import OpenAI

from src.core.config import config
from src.llm.prompts import REPAIR_PROMPT_TEMPLATE, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from src.llm.schema import DataFrameSchemaExtractor


class DeepSeekClient:
    """Cliente para interagir com a API da DeepSeek com suporte a Workbooks multi-abas."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or config.api_key
        self.base_url = base_url or config.base_url
        self.model = model or config.default_model

        if not self.api_key:
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def is_configured(self) -> bool:
        """Verifica se o cliente está configurado com uma chave de API."""
        return self.client is not None and bool(self.api_key and len(self.api_key.strip()) > 5)

    def _extract_code_and_explanation(self, response_text: str) -> Tuple[str, str]:
        """
        Extrai o bloco de código Python e o texto explicativo da resposta do LLM.
        """
        code_match = re.search(r"```(?:python)?\s*([\s\S]*?)```", response_text, re.IGNORECASE)
        if code_match:
            code = code_match.group(1).strip()
        else:
            code = response_text.strip()

        explanation = ""
        explanation_markers = [
            "### EXPLICAÇÃO:", "### EXPLICACAO:",
            "### EXPLICAÇÃO", "### EXPLICACAO",
            "EXPLICAÇÃO:", "EXPLICACAO:"
        ]
        for marker in explanation_markers:
            if marker in response_text:
                parts = response_text.split(marker)
                explanation = parts[-1].strip()
                break

        if not explanation:
            clean_text = re.sub(r"```(?:python)?[\s\S]*?```", "", response_text).strip()
            explanation = clean_text if clean_text else "Manipulação realizada com sucesso."

        return code, explanation

    def generate_transformation(
        self,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        user_instruction: str,
        temperature: float = 0.1,
    ) -> Tuple[str, str]:
        """
        Gera código Python/Pandas e explicação com base no DataFrame ou dicionário de abas.
        Retorna (codigo_python, explicacao_pt_br).
        """
        if not self.is_configured():
            raise ValueError("Chave de API DeepSeek não configurada. Por favor, forneça sua API Key.")

        schema_text = DataFrameSchemaExtractor.format_schema_for_prompt(
            data, max_sample_rows=config.sample_rows_for_schema
        )
        user_prompt = USER_PROMPT_TEMPLATE.format(
            schema_text=schema_text,
            user_instruction=user_instruction,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )
            content = response.choices[0].message.content or ""
            return self._extract_code_and_explanation(content)
        except Exception as e:
            raise RuntimeError(f"Erro ao comunicar com a API DeepSeek: {str(e)}")

    def repair_transformation(
        self,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        user_instruction: str,
        failed_code: str,
        error_message: str,
        temperature: float = 0.1,
    ) -> Tuple[str, str]:
        """
        Solicita à DeepSeek a correção de um código que falhou em tempo de execução.
        """
        if not self.is_configured():
            raise ValueError("Chave de API DeepSeek não configurada.")

        schema_text = DataFrameSchemaExtractor.format_schema_for_prompt(
            data, max_sample_rows=config.sample_rows_for_schema
        )
        repair_prompt = REPAIR_PROMPT_TEMPLATE.format(
            schema_text=schema_text,
            user_instruction=user_instruction,
            failed_code=failed_code,
            error_message=error_message,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": repair_prompt},
                ],
                temperature=temperature,
            )
            content = response.choices[0].message.content or ""
            return self._extract_code_and_explanation(content)
        except Exception as e:
            raise RuntimeError(f"Erro no auto-healing com DeepSeek: {str(e)}")
