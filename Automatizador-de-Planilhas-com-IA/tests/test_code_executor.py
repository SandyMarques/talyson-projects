"""Testes do executor isolado (`SafeCodeExecutor`) com suporte multi-abas.

Estratégia (pirâmide de testes + quadrantes de Crispin/Gregory):
- Q1 unitário: `CodeSafetyValidator` — lógica pura, sem I/O, milissegundos.
- Q1 integração: `SafeCodeExecutor.execute` — exercita o subprocesso isolado real, porque é
  justamente o isolamento que está sob teste (um fake aqui não provaria nada).
- Q4 segurança: a suíte adversarial vive em `test_security_sandbox.py`.

Determinismo: cada teste cria o próprio DataFrame; não há estado compartilhado, relógio nem
rede. O subprocesso é determinístico para as transformações testadas.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.engine.code_executor import (
    CodeSafetyError,
    CodeSafetyValidator,
    ExecutionResult,
    SafeCodeExecutor,
    SandboxLimits,
)


@pytest.fixture(scope="module")
def executor() -> SafeCodeExecutor:
    """Executor real (subprocesso isolado) compartilhado pelos testes do módulo."""
    return SafeCodeExecutor()


@pytest.fixture
def df_simples() -> pd.DataFrame:
    return pd.DataFrame({"Qtd": [2, 5, 10], "Preco": [10.0, 20.0, 5.0]})


# ---------------------------------------------------------------------------------------
# Q1 - Unitários: validação estática (AST), sem subprocesso
# ---------------------------------------------------------------------------------------


class TestValidacaoEstatica:
    """O validador é lógica pura: rápido, sem I/O, testável isoladamente."""

    def test_aceita_codigo_legitimo(self):
        codigo = (
            "df_result = df.copy()\n"
            "df_result['Total'] = pd.to_numeric(df_result['Qtd'], errors='coerce') * 2\n"
            "df_result = df_result[df_result['Total'] > np.float64(0)]"
        )
        valido, motivo = CodeSafetyValidator().check(codigo)
        assert valido is True, motivo

    def test_rejeita_import_de_modulo_perigoso(self):
        for modulo in ("os", "sys", "subprocess", "socket", "shutil", "ctypes", "requests"):
            valido, motivo = CodeSafetyValidator().check(f"import {modulo}\ndf_result = df")
            assert valido is False, f"import de {modulo} deveria ser rejeitado"
            assert "não é permitido" in motivo

    def test_rejeita_import_from(self):
        valido, motivo = CodeSafetyValidator().check("from os import environ\ndf_result = df")
        assert valido is False
        assert "os" in motivo

    def test_rejeita_import_relativo(self):
        valido, _ = CodeSafetyValidator().check("from . import utils\ndf_result = df")
        assert valido is False

    @pytest.mark.parametrize(
        "codigo",
        [
            "df_result = df.__class__",
            "df_result = df.__globals__",
            "df_result = df.__subclasses__()",
            "df_result = str.__mro__",
            "df_result = (5).__class__.__bases__",
        ],
    )
    def test_rejeita_acesso_a_dunder(self, codigo):
        valido, _ = CodeSafetyValidator().check(codigo)
        assert valido is False

    @pytest.mark.parametrize(
        "codigo",
        [
            "df_result = eval('1+1')",
            "exec('x=1')\ndf_result = df",
            "df_result = open('x.txt')",
            "df_result = __import__('os')",
            "df_result = getattr(df, '__class__')",
            "df_result = setattr(df, 'x', 1)",
            "df_result = compile('1', 'a', 'eval')",
            "df_result = globals()",
            "df_result = input()",
        ],
    )
    def test_rejeita_builtins_perigosos(self, codigo):
        valido, motivo = CodeSafetyValidator().check(codigo)
        assert valido is False, f"{codigo!r} deveria ser rejeitado"
        assert motivo

    def test_rejeita_leitura_de_arquivo_do_pandas(self):
        for chamada in ("pd.read_csv('x.csv')", "pd.read_excel('x.xlsx')", "pd.read_pickle('x')"):
            valido, _ = CodeSafetyValidator().check(f"df_result = {chamada}")
            assert valido is False, chamada

    def test_rejeita_escrita_de_arquivo_do_pandas(self):
        valido, _ = CodeSafetyValidator().check("df.to_csv('x.csv')\ndf_result = df")
        assert valido is False
        valido, _ = CodeSafetyValidator().check("df_result = df.to_excel('x.xlsx')")
        assert valido is False

    def test_rejeita_reatribuicao_de_entradas_do_sandbox(self):
        """`pd = ...` sobrescreveria o módulo e quebraria silenciosamente as linhas seguintes."""
        for alvo in ("pd", "np", "df", "dfs"):
            valido, motivo = CodeSafetyValidator().check(f"{alvo} = 1\ndf_result = df")
            assert valido is False, alvo
            assert "reatribuir" in motivo

    def test_permite_atribuir_saidas(self):
        valido, motivo = CodeSafetyValidator().check(
            "df_result = df\ndfs_result = {'a': df}"
        )
        assert valido is True, motivo

    def test_rejeita_codigo_vazio(self):
        valido, motivo = CodeSafetyValidator().check("   ")
        assert valido is False
        assert "Nenhum código" in motivo

    def test_rejeita_sintaxe_invalida(self):
        valido, motivo = CodeSafetyValidator().check("df_result = = df")
        assert valido is False
        assert "não é Python válido" in motivo

    def test_ofuscacao_por_concatenacao_nao_contorna_ast(self):
        """A AST não é enganada por strings montadas em runtime (o regex antigo era)."""
        codigo = "nome = 'o' + 's'\nimport os\ndf_result = df"
        valido, _ = CodeSafetyValidator().check(codigo)
        assert valido is False

    def test_validate_levanta_excecao(self):
        with pytest.raises(CodeSafetyError):
            CodeSafetyValidator().validate("import os")


# ---------------------------------------------------------------------------------------
# Q1 - Integração: execução no subprocesso isolado
# ---------------------------------------------------------------------------------------


class TestExecucaoIsolada:
    """Exercita o subprocesso real: é o isolamento que está sob teste."""

    def test_atribuicao_simples(self, executor, df_simples):
        result = executor.execute(
            "df_result = df.copy()\n"
            "df_result['Total'] = df_result['Qtd'] * df_result['Preco']",
            df_simples,
        )
        assert result.success is True, result.error
        assert "Total" in result.df_result.columns
        assert list(result.df_result["Total"]) == [20.0, 100.0, 50.0]
        assert result.columns_added == ["Total"]
        assert result.rows_delta == 0

    def test_modificacao_inplace_de_df(self, executor):
        df = pd.DataFrame({"A": [1, 2, 3]})
        result = executor.execute("df['B'] = df['A'] * 2", df)
        assert result.success is True, result.error
        assert list(result.df_result["B"]) == [2, 4, 6]

    def test_entrada_original_nao_e_mutada(self, executor):
        df = pd.DataFrame({"A": [1, 2]})
        original = df.copy(deep=True)
        executor.execute("df['A'] = 999\ndf_result = df", df)
        pd.testing.assert_frame_equal(df, original)

    def test_multi_abas_merge(self, executor):
        dfs = {
            "Vendas": pd.DataFrame({"ID_Cli": [1, 2], "Valor": [100, 200]}),
            "Clientes": pd.DataFrame({"ID_Cli": [1, 2], "Nome": ["Ana", "Carlos"]}),
        }
        result = executor.execute(
            "df_result = pd.merge(dfs['Vendas'], dfs['Clientes'], on='ID_Cli')", dfs
        )
        assert result.success is True, result.error
        assert list(result.df_result.columns) == ["ID_Cli", "Valor", "Nome"]
        assert len(result.df_result) == 2

    def test_multi_abas_dfs_result(self, executor):
        dfs = {"A": pd.DataFrame({"x": [1]}), "B": pd.DataFrame({"x": [2]})}
        result = executor.execute(
            "dfs_result = {'Uniao': pd.concat([dfs['A'], dfs['B']], ignore_index=True)}", dfs
        )
        assert result.success is True, result.error
        assert "Uniao" in result.dfs_result
        assert len(result.dfs_result["Uniao"]) == 2

    def test_atribuicao_com_tipos_do_pandas(self, executor):
        df = pd.DataFrame({"V": [1.234, 9.876]})
        result = executor.execute(
            "df_result = df.assign(r=round(df['V'], 1), "
            "c=np.select([df['V'] > 5], ['alta'], default='baixa'))",
            df,
        )
        assert result.success is True, result.error
        assert list(result.df_result["c"]) == ["baixa", "alta"]

    def test_funcao_auxiliar_definida_no_snippet(self, executor):
        df = pd.DataFrame({"V": [1.5, 2.5]})
        result = executor.execute(
            "def dobro(x):\n    return x * 2\ndf_result = df.assign(V2=df['V'].map(dobro))",
            df,
        )
        assert result.success is True, result.error
        assert list(result.df_result["V2"]) == [3.0, 5.0]

    def test_captura_de_stdout(self, executor):
        df = pd.DataFrame({"A": [1]})
        result = executor.execute("print('diagnostico')\ndf_result = df", df)
        assert result.success is True
        assert "diagnostico" in result.stdout

    def test_erro_de_execucao_devolve_traceback(self, executor):
        df = pd.DataFrame({"A": [1, 2]})
        result = executor.execute("df_result = df['Coluna_Inexistente'] + 10", df)
        assert result.success is False
        assert result.df_result is None
        assert "Coluna_Inexistente" in f"{result.error}{result.traceback}"

    def test_sem_dataframe_de_saida(self, executor):
        """`x = 42` não produz saída; devolver o `df` de entrada mascararia o erro."""
        df = pd.DataFrame({"A": [1]})
        result = executor.execute("x = 42", df)
        assert result.success is False
        # Asserção em fragmento sem acento: independe do encoding com que o Python lê o teste.
        assert "pandas DataFrame" in str(result.error)
        assert "df_result" in str(result.error)

    def test_entrada_inalterada_nao_vira_resultado(self, executor):
        df = pd.DataFrame({"A": [1, 2]})
        result = executor.execute("copia = df.copy()", df)
        assert result.success is False

    def test_entrada_vazia(self, executor):
        result = executor.execute("df_result = df", {})
        assert result.success is False
        assert "Nenhuma aba" in str(result.error)

    def test_limite_de_celulas_impede_execucao(self, df_simples):
        executor = SafeCodeExecutor(SandboxLimits(max_cells=2))
        result = executor.execute("df_result = df", df_simples)
        assert result.success is False
        assert "acima do limite" in str(result.error)

    def test_timeout_interrompe_laco_infinito(self):
        executor = SafeCodeExecutor(SandboxLimits(wall_timeout_seconds=6, cpu_seconds=4))
        df = pd.DataFrame({"A": [1]})
        result = executor.execute("while True:\n    pass\ndf_result = df", df)
        assert result.success is False
        assert "excedeu o limite" in str(result.error)

    def test_resultado_preserva_datas_e_categorias(self, executor):
        """Datas e categorias precisam sobreviver ao transporte JSON do sandbox."""
        df = pd.DataFrame({
            "data": pd.to_datetime(["2024-01-01", "2024-06-15"]),
            "categoria": pd.Categorical(["a", "b"]),
            "valor": [1.5, 2.5],
        })
        result = executor.execute("df_result = df", df)
        assert result.success is True, result.error
        assert len(result.df_result) == 2
        assert result.df_result["valor"].tolist() == [1.5, 2.5]


# ---------------------------------------------------------------------------------------
# Contrato e retrocompatibilidade
# ---------------------------------------------------------------------------------------


class TestContrato:
    def test_api_de_classe_validate_code_safety_preservada(self):
        valido, motivo = SafeCodeExecutor.validate_code_safety("df_result = df")
        assert valido is True
        assert motivo is None

        valido, motivo = SafeCodeExecutor.validate_code_safety("import os")
        assert valido is False
        assert motivo

    def test_execution_result_tem_os_campos_esperados(self, executor, df_simples):
        result = executor.execute("df_result = df", df_simples)
        assert isinstance(result, ExecutionResult)
        for campo in (
            "success",
            "df_result",
            "dfs_result",
            "executed_code",
            "stdout",
            "execution_time_ms",
            "columns_added",
            "columns_removed",
            "rows_delta",
        ):
            assert hasattr(result, campo)
