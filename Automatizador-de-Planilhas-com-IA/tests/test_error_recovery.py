"""Testes para o pipeline de auto-recuperação (Auto-Healing) com suporte multi-abas.

Estratégia de doubles: o cliente LLM é um **Mock** (`MagicMock(spec=DeepSeekClient)`), porque o
contrato de interação (quantas gerações, quantos reparos, em que ordem) é justamente o que o
loop promete. O executor é o real — o sandbox em subprocesso —, então os testes também validam
que código bloqueado por segurança conta como falha e aciona o auto-healing.
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest
from openai import APIStatusError, RateLimitError

from src.engine.error_recovery import TransformationPipeline
from src.llm.client import DeepSeekClient


def test_pipeline_success_first_try():
    """Valida fluxo direto bem-sucedido na 1ª tentativa."""
    mock_client = MagicMock(spec=DeepSeekClient)
    mock_client.generate_transformation.return_value = (
        "df_result = df.copy()\ndf_result['Total'] = df_result['Preco'] * 2",
        "Multiplicou preço por 2."
    )

    df = pd.DataFrame({"Preco": [10, 20]})
    pipeline = TransformationPipeline(client=mock_client, max_retries=2)
    result = pipeline.run(df, "Multiplique o preço por 2")

    assert result.success is True
    assert result.total_attempts == 1
    assert result.healing_applied is False
    assert "Total" in result.final_df.columns
    assert list(result.final_df["Total"]) == [20, 40]


def test_pipeline_multi_sheet_success():
    """Valida fluxo com dicionário multi-abas."""
    mock_client = MagicMock(spec=DeepSeekClient)
    mock_client.generate_transformation.return_value = (
        "df_result = pd.merge(dfs['Vendas'], dfs['Clientes'], on='ID')",
        "Cruzou abas Vendas e Clientes."
    )

    dfs = {
        "Vendas": pd.DataFrame({"ID": [1, 2], "Qtd": [5, 10]}),
        "Clientes": pd.DataFrame({"ID": [1, 2], "Nome": ["Ana", "Bob"]}),
    }
    pipeline = TransformationPipeline(client=mock_client, max_retries=2)
    result = pipeline.run(dfs, "Cruze Vendas e Clientes")

    assert result.success is True
    assert result.total_attempts == 1
    assert "Nome" in result.final_df.columns
    assert "Qtd" in result.final_df.columns


def test_pipeline_auto_healing_recovery():
    """Valida que o auto-healing corrige um código que falhou na 1ª tentativa."""
    mock_client = MagicMock(spec=DeepSeekClient)
    
    # 1ª tentativa gera código com erro (coluna errada 'Valor')
    mock_client.generate_transformation.return_value = (
        "df_result = df['Valor'] * 2",
        "Tentou multiplicar Valor."
    )
    # 2ª tentativa (repair) corrige para 'Preco'
    mock_client.repair_transformation.return_value = (
        "df_result = df.copy()\ndf_result['Total'] = df_result['Preco'] * 2",
        "Corrigido nome da coluna para Preco."
    )

    df = pd.DataFrame({"Preco": [10, 20]})
    pipeline = TransformationPipeline(client=mock_client, max_retries=2)
    result = pipeline.run(df, "Multiplique o preço por 2")

    assert result.success is True
    assert result.total_attempts == 2
    assert result.healing_applied is True
    assert "Total" in result.final_df.columns
    mock_client.repair_transformation.assert_called_once()


# ---------------------------------------------------------------------------------------
# Casos de borda e regressões do loop de auto-healing
# ---------------------------------------------------------------------------------------


class TestLoopDeAutoHealing:
    """O loop é finito por construção; o que precisa ser coberto são os modos de falha."""

    def test_loop_e_limitado_por_max_retries(self):
        """Nunca deve gerar mais chamadas que 1 geração + N reparos."""
        mock_client = MagicMock(spec=DeepSeekClient)
        mock_client.generate_transformation.return_value = ("df_result = df['NaoExiste']", "erro")
        mock_client.repair_transformation.return_value = ("df_result = df['TambemNao']", "erro")

        pipeline = TransformationPipeline(client=mock_client, max_retries=2)
        result = pipeline.run(pd.DataFrame({"A": [1]}), "faça algo")

        assert result.success is False
        assert result.total_attempts == 3  # 1 inicial + 2 reparos
        assert mock_client.repair_transformation.call_count == 2

    def test_erro_de_geracao_devolve_mensagem_de_comunicacao(self):
        mock_client = MagicMock(spec=DeepSeekClient)
        mock_client.generate_transformation.side_effect = RuntimeError("HTTP 401")

        result = TransformationPipeline(client=mock_client).run(pd.DataFrame({"A": [1]}), "x")
        assert result.success is False
        assert "Falha na comunicação" in result.error_message
        assert "HTTP 401" in result.error_message

    def test_falha_do_reparo_nao_devolve_erro_none(self):
        """Regressão: `except Exception: break` deixava `error_message=None`."""
        mock_client = MagicMock(spec=DeepSeekClient)
        mock_client.generate_transformation.return_value = ("df_result = df['NaoExiste']", "erro")
        mock_client.repair_transformation.side_effect = RuntimeError("rate limit")

        result = TransformationPipeline(client=mock_client, max_retries=2).run(
            pd.DataFrame({"A": [1]}), "x"
        )
        assert result.success is False
        assert result.error_message is not None
        assert "NaoExiste" in result.error_message
        assert "auto-healing" in result.error_message.lower()

    def test_codigo_bloqueado_pelo_sandbox_conta_como_falha(self):
        """Código que tenta escapar deve falhar e acionar o auto-healing, não executar."""
        mock_client = MagicMock(spec=DeepSeekClient)
        mock_client.generate_transformation.return_value = (
            "import os\ndf_result = df.assign(v=os.getcwd())",
            "tentou ler o sistema",
        )
        mock_client.repair_transformation.return_value = ("df_result = df.copy()", "corrigido")

        result = TransformationPipeline(client=mock_client, max_retries=1).run(
            pd.DataFrame({"A": [1]}), "x"
        )
        assert result.success is True
        assert result.healing_applied is True
        assert result.attempts_history[0].execution_result.success is False
        assert "segurança" in result.attempts_history[0].execution_result.error

    def test_historico_de_tentativas_e_auditavel(self):
        mock_client = MagicMock(spec=DeepSeekClient)
        mock_client.generate_transformation.return_value = ("df_result = df['NaoExiste']", "e1")
        mock_client.repair_transformation.return_value = (
            "df_result = df.assign(B=df['A'] * 2)",
            "e2",
        )

        result = TransformationPipeline(client=mock_client, max_retries=1).run(
            pd.DataFrame({"A": [1]}), "x"
        )
        assert len(result.attempts_history) == 2
        assert result.attempts_history[0].was_repaired is False
        assert result.attempts_history[1].was_repaired is True
        assert all(tentativa.code for tentativa in result.attempts_history)
        assert all(tentativa.explanation for tentativa in result.attempts_history)


class TestConfiguracaoDoCliente:
    """O cliente precisa aplicar timeout e temperatura de verdade."""

    def test_temperature_do_slider_e_respeitada(self):
        """Regressão: o slider era coletado na UI e o valor hardcoded 0.1 era usado."""
        cliente = DeepSeekClient(api_key="sk-teste-valido-123", temperature=0.75)
        assert cliente.temperature == 0.75

    def test_timeout_explicito_no_sdk(self):
        """Sem timeout explícito o SDK assume 600s e a interface parece travada."""
        from src.core.config import config

        cliente = DeepSeekClient(api_key="sk-teste-valido-123")
        assert cliente.timeout_seconds == config.timeout_seconds
        assert cliente.timeout_seconds <= 120

    def test_sem_chave_nao_instancia_cliente(self):
        cliente = DeepSeekClient(api_key="")
        assert cliente.client is None
        assert cliente.is_configured() is False

    def test_erro_acionavel_quando_sem_chave(self):
        from src.llm.client import LLMConnectionError

        cliente = DeepSeekClient(api_key="")
        with pytest.raises(LLMConnectionError, match="não configurada"):
            cliente.generate_transformation(pd.DataFrame({"A": [1]}), "x")

    def test_erro_http_vira_mensagem_acionavel(self):
        from src.llm.client import LLMConnectionError

        cliente = DeepSeekClient(api_key="sk-teste-valido-123")
        erro = APIStatusError("invalid key", response=MagicMock(status_code=401), body=None)
        erro.status_code = 401
        cliente.client = MagicMock()
        cliente.client.chat.completions.create.side_effect = erro

        with pytest.raises(LLMConnectionError, match="recusada"):
            cliente.generate_transformation(pd.DataFrame({"A": [1]}), "x")

    def test_erro_429_indica_limite_de_uso(self):
        from src.llm.client import LLMConnectionError

        cliente = DeepSeekClient(api_key="sk-teste-valido-123")
        resposta = MagicMock(status_code=429)
        cliente.client = MagicMock()
        cliente.client.chat.completions.create.side_effect = RateLimitError(
            "rate limit", response=resposta, body=None
        )

        with pytest.raises(LLMConnectionError, match="429"):
            cliente.generate_transformation(pd.DataFrame({"A": [1]}), "x")

    def test_max_tokens_e_enviado(self):
        """Sem teto de tokens a resposta divaga e o custo fica imprevisível."""
        from src.core.config import config

        cliente = DeepSeekClient(api_key="sk-teste-valido-123")
        cliente.client = MagicMock()
        resposta = MagicMock()
        resposta.choices = [MagicMock(message=MagicMock(content="```python\nx = 1\n```"))]
        cliente.client.chat.completions.create.return_value = resposta

        cliente.generate_transformation(pd.DataFrame({"A": [1]}), "x")
        kwargs = cliente.client.chat.completions.create.call_args.kwargs
        assert kwargs["max_tokens"] == config.max_tokens
        assert kwargs["temperature"] == cliente.temperature
