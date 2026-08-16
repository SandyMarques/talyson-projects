"""Testes para o pipeline de auto-recuperação (Auto-Healing) com suporte multi-abas."""

from unittest.mock import MagicMock
import pandas as pd
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
