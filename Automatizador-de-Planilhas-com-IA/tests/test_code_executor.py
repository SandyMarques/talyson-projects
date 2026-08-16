"""Testes para a sandbox de execução segura (SafeCodeExecutor) com suporte multi-abas."""

import pandas as pd
from src.engine.code_executor import SafeCodeExecutor


def test_successful_execution_single_df():
    """Valida execução correta de código Pandas com único DataFrame."""
    df = pd.DataFrame({
        "Qtd": [2, 5, 10],
        "Preco": [10.0, 20.0, 5.0]
    })
    code = """
df_result = df.copy()
df_result['Total'] = df_result['Qtd'] * df_result['Preco']
"""
    result = SafeCodeExecutor.execute(code, df)
    assert result.success is True
    assert result.df_result is not None
    assert "Total" in result.df_result.columns
    assert list(result.df_result["Total"]) == [20.0, 100.0, 50.0]
    assert result.columns_added == ["Total"]
    assert result.rows_delta == 0


def test_successful_cross_sheet_execution():
    """Valida execução entre múltiplas abas via dicionário dfs."""
    dfs = {
        "Vendas": pd.DataFrame({"ID_Cli": [1, 2], "Valor": [100, 200]}),
        "Clientes": pd.DataFrame({"ID_Cli": [1, 2], "Nome": ["Ana", "Carlos"]})
    }
    code = """
vendas = dfs['Vendas']
clientes = dfs['Clientes']
df_result = pd.merge(vendas, clientes, on='ID_Cli')
"""
    result = SafeCodeExecutor.execute(code, dfs)
    assert result.success is True
    assert result.df_result is not None
    assert list(result.df_result.columns) == ["ID_Cli", "Valor", "Nome"]
    assert len(result.df_result) == 2


def test_inplace_df_modification():
    """Valida código que modifica 'df' sem atribuir explicitamente a 'df_result'."""
    df = pd.DataFrame({"A": [1, 2, 3]})
    code = "df['B'] = df['A'] * 2"
    result = SafeCodeExecutor.execute(code, df)
    assert result.success is True
    assert "B" in result.df_result.columns
    assert list(result.df_result["B"]) == [2, 4, 6]


def test_security_blocking_os_import():
    """Valida que importação de módulos perigosos é bloqueada estaticamente."""
    df = pd.DataFrame({"A": [1, 2]})
    code = """
import os
df_result = df.copy()
"""
    result = SafeCodeExecutor.execute(code, df)
    assert result.success is False
    assert "não permitida por segurança" in result.error


def test_security_blocking_eval_open():
    """Valida que chamadas de open/eval são bloqueadas."""
    df = pd.DataFrame({"A": [1, 2]})
    code = "eval('1 + 1')"
    result = SafeCodeExecutor.execute(code, df)
    assert result.success is False
    assert "não permitida por segurança" in result.error


def test_runtime_error_handling():
    """Valida que erros de execução em tempo de execução retornam resultado com falha e traceback."""
    df = pd.DataFrame({"A": [1, 2]})
    code = "df_result = df['Coluna_Inexistente'] + 10"
    result = SafeCodeExecutor.execute(code, df)
    assert result.success is False
    assert result.df_result is None
    assert result.error is not None
    assert result.traceback is not None
