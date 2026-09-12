"""Cliente DeepSeek utilizando o SDK compatível com OpenAI e suporte a múltiplas abas."""

import re
from typing import Any, Dict, Optional, Tuple, Union

import pandas as pd
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from src.core.config import config
from src.llm.prompts import REPAIR_PROMPT_TEMPLATE, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from src.llm.schema import DataFrameSchemaExtractor


class LLMConnectionError(RuntimeError):
    """Falha acionável de comunicação com o provedor de LLM.

    Distingue chave inválida de limite de uso e de indisponibilidade — a versão anterior
    embrulhava tudo em um `RuntimeError` genérico e apagava o status HTTP.
    """


class DeepSeekClient:
    """Cliente para interagir com a API da DeepSeek com suporte a Workbooks multi-abas."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self.api_key = api_key or config.api_key
        self.base_url = base_url or config.base_url
        self.model = model or config.default_model
        self.temperature = (
            temperature if temperature is not None else config.temperature
        )
        # O usuário escolhe no slider; antes o valor era coletado e ignorado (hardcoded 0.1).
        self.timeout_seconds = timeout_seconds or config.timeout_seconds

        if not self.api_key:
            self.client = None
        else:
            # timeout explícito: o default do SDK é 600s, o que trava a interface sem aviso.
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                max_retries=1,
            )

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

    # -- Comunicação -------------------------------------------------------------------

    def _chamar_modelo(self, prompt_usuario: str) -> str:
        """Chama o provedor traduzindo falhas em mensagens acionáveis."""
        if not self.is_configured():
            raise LLMConnectionError(
                "Chave de API DeepSeek não configurada. Informe a chave na barra lateral "
                "ou defina DEEPSEEK_API_KEY no arquivo .env."
            )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_usuario},
                ],
                temperature=self.temperature,
                max_tokens=config.max_tokens,
            )
        except APITimeoutError as exc:
            raise LLMConnectionError(
                f"A API não respondeu em {self.timeout_seconds:.0f}s. "
                "Tente novamente ou reduza o volume de dados enviado."
            ) from exc
        except RateLimitError as exc:
            raise LLMConnectionError(
                "Limite de uso da API atingido (HTTP 429). Aguarde alguns instantes."
            ) from exc
        except APIStatusError as exc:
            detalhe = getattr(exc, "message", "") or str(exc)
            if exc.status_code in (401, 403):
                raise LLMConnectionError(
                    f"A chave de API foi recusada pelo provedor (HTTP {exc.status_code}). "
                    "Confira DEEPSEEK_API_KEY."
                ) from exc
            if exc.status_code == 402:
                raise LLMConnectionError(
                    "Saldo/créditos insuficientes na conta do provedor (HTTP 402)."
                ) from exc
            raise LLMConnectionError(
                f"Erro do provedor (HTTP {exc.status_code}): {detalhe[:200]}"
            ) from exc
        except APIConnectionError as exc:
            raise LLMConnectionError(
                f"Não foi possível conectar a {self.base_url}. Verifique a rede ou a Base URL."
            ) from exc

        conteudo = response.choices[0].message.content if response.choices else ""
        return conteudo or ""

    def generate_transformation(
        self,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        user_instruction: str,
    ) -> Tuple[str, str]:
        """
        Gera código Python/Pandas e explicação com base no DataFrame ou dicionário de abas.
        Retorna (codigo_python, explicacao_pt_br).
        """
        schema_text = DataFrameSchemaExtractor.format_schema_for_prompt(
            data,
            max_sample_rows=config.sample_rows_for_schema,
            max_prompt_chars=config.max_prompt_chars,
        )
        user_prompt = USER_PROMPT_TEMPLATE.format(
            schema_text=schema_text,
            user_instruction=user_instruction,
        )
        return self._extract_code_and_explanation(self._chamar_modelo(user_prompt))

    def repair_transformation(
        self,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        user_instruction: str,
        failed_code: str,
        error_message: str,
    ) -> Tuple[str, str]:
        """
        Solicita à DeepSeek a correção de um código que falhou em tempo de execução.
        """
        schema_text = DataFrameSchemaExtractor.format_schema_for_prompt(
            data,
            max_sample_rows=config.sample_rows_for_schema,
            max_prompt_chars=config.max_prompt_chars,
        )
        repair_prompt = REPAIR_PROMPT_TEMPLATE.format(
            schema_text=schema_text,
            user_instruction=user_instruction,
            failed_code=failed_code[:4000],
            error_message=error_message[:2000],
        )
        return self._extract_code_and_explanation(self._chamar_modelo(repair_prompt))
