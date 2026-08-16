"""Testes para o manipulador de arquivos (FileHandler) com suporte multi-abas."""

import io
import pandas as pd
import pytest
from src.core.file_handler import FileHandler


def test_sample_ecommerce_data():
    """Valida a geração do dataset de exemplo simples."""
    df = FileHandler.get_sample_ecommerce_data()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 10
    assert "Preco_Unitario" in df.columns
    assert "Quantidade" in df.columns


def test_sample_ecommerce_workbook():
    """Valida a geração do workbook multi-abas de exemplo."""
    workbook = FileHandler.get_sample_ecommerce_workbook()
    assert isinstance(workbook, dict)
    assert "Vendas" in workbook
    assert "Clientes" in workbook
    assert "Produtos" in workbook
    assert "Metas" in workbook
    assert len(workbook["Vendas"]) > 0
    assert len(workbook["Clientes"]) > 0


def test_load_csv_comma():
    """Valida carregamento de CSV separado por vírgula."""
    csv_content = "Nome,Idade,Cidade\nAlice,30,Sao Paulo\nBruno,25,Rio de Janeiro\n"
    df, meta = FileHandler.load_csv(csv_content.encode("utf-8"))
    assert len(df) == 2
    assert list(df.columns) == ["Nome", "Idade", "Cidade"]
    assert meta["delimiter"] == ","


def test_load_csv_semicolon():
    """Valida carregamento de CSV separado por ponto e vírgula."""
    csv_content = "Produto;Valor;Estoque\nCamisa;59.90;100\nCalca;120.00;50\n"
    df, meta = FileHandler.load_csv(csv_content.encode("utf-8"))
    assert len(df) == 2
    assert list(df.columns) == ["Produto", "Valor", "Estoque"]
    assert meta["delimiter"] == ";"


def test_export_and_load_excel_multi_sheet():
    """Valida exportação e leitura de Excel com múltiplas abas."""
    wb = {
        "AbaVendas": pd.DataFrame({"ID": [1, 2], "Valor": [100, 200]}),
        "AbaClientes": pd.DataFrame({"ID": [1, 2], "Nome": ["Ana", "Bob"]}),
    }
    
    excel_bytes = FileHandler.export_to_excel_bytes(wb)
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0

    # Ler todas as abas
    loaded_dfs, meta = FileHandler.load_all_sheets(excel_bytes, "arquivo.xlsx")
    assert len(loaded_dfs) == 2
    assert "AbaVendas" in loaded_dfs
    assert "AbaClientes" in loaded_dfs
    assert list(loaded_dfs["AbaVendas"].columns) == ["ID", "Valor"]
    assert list(loaded_dfs["AbaClientes"].columns) == ["ID", "Nome"]


def test_export_to_csv_bytes():
    """Valida a exportação para bytes CSV."""
    df = pd.DataFrame({"A": [1, 2], "B": ["X", "Y"]})
    csv_bytes = FileHandler.export_to_csv_bytes(df, sep=";")
    assert isinstance(csv_bytes, bytes)
    assert b"A;B" in csv_bytes
