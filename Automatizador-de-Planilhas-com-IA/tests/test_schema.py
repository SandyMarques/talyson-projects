"""Testes para o extrator de esquema (DataFrameSchemaExtractor) com suporte multi-abas."""

import pandas as pd
from src.llm.schema import DataFrameSchemaExtractor


def test_extract_summary():
    """Valida a extração estruturada de metadados do DataFrame."""
    df = pd.DataFrame({
        "Nome": ["Ana", "Carlos", "Beatriz", None],
        "Idade": [25, 30, 22, 40],
        "Status": ["Ativo", "Ativo", "Inativo", "Ativo"],
    })

    summary = DataFrameSchemaExtractor.extract_summary(df, max_sample_rows=3)
    assert summary["total_rows"] == 4
    assert summary["total_columns"] == 3
    assert len(summary["columns"]) == 3

    nome_col = next(c for c in summary["columns"] if c["name"] == "Nome")
    assert nome_col["null_count"] == 1

    status_col = next(c for c in summary["columns"] if c["name"] == "Status")
    assert "unique_sample" in status_col
    assert "Ativo" in status_col["unique_sample"]


def test_format_schema_for_single_df():
    """Valida a formatação de texto para uma única tabela."""
    df = pd.DataFrame({
        "Produto": ["Teclado", "Mouse"],
        "Preco": [150.0, 80.0]
    })
    schema_text = DataFrameSchemaExtractor.format_schema_for_prompt(df)
    assert "TABELA" in schema_text or "ABA" in schema_text
    assert "Produto" in schema_text
    assert "Preco" in schema_text


def test_format_schema_for_multi_sheet():
    """Valida a formatação de texto para múltiplas abas."""
    dfs = {
        "Vendas": pd.DataFrame({"ID_Venda": [1, 2], "Valor": [50.0, 120.0]}),
        "Clientes": pd.DataFrame({"ID_Cliente": [10, 20], "Nome": ["Alpha", "Beta"]}),
    }
    schema_text = DataFrameSchemaExtractor.format_schema_for_prompt(dfs)
    assert "ESTRUTURA DO WORKBOOK" in schema_text
    assert "Vendas" in schema_text
    assert "Clientes" in schema_text
    assert "ID_Venda" in schema_text
    assert "ID_Cliente" in schema_text
