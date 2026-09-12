"""Suíte adversarial do sandbox (Quadrante Q4 - testes que criticam o produto).

Objetivo: tentar QUEBRAR o isolamento, não confirmar que ele existe. Todos os cenários
abaixo passavam com a implementação anterior (blocklist de regex + `exec` no processo da
aplicação) e falham agora. Se algum voltar a passar, é regressão de segurança.

Critério de sucesso dos testes NÃO é "retornou erro com a mensagem bonita": é **o efeito
perigoso não ter acontecido** (arquivo não criado, segredo não exposto, comando não
executado). Mensagem, código de erro e traceback são livres para mudar.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from src.engine.code_executor import SafeCodeExecutor

#: Segredo plantado no ambiente do processo de teste. O sandbox limpa o ambiente do filho,
#: então este valor NUNCA pode aparecer em nenhum resultado.
SEGREDO = "sk-adversarial-nao-deve-vazar-9f3a"
USUARIO = os.environ.get("USERNAME") or os.environ.get("USER") or ""


@pytest.fixture(scope="module")
def executor() -> SafeCodeExecutor:
    return SafeCodeExecutor()


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})


@pytest.fixture(autouse=True)
def ambiente_com_segredo(monkeypatch):
    """Planta um segredo no ambiente para provar que ele não atravessa o sandbox."""
    monkeypatch.setenv("PROBE_SECRET", SEGREDO)
    return SEGREDO


@dataclass
class Observacao:
    """O que realmente aconteceu no mundo real após a tentativa de ataque."""

    sucesso: bool
    erro: str
    texto_resultante: str


def _observar(executor: SafeCodeExecutor, codigo: str, df: pd.DataFrame) -> Observacao:
    resultado = executor.execute(codigo, df)
    texto = ""
    if resultado.df_result is not None:
        texto += resultado.df_result.to_json(force_ascii=False)
    if resultado.dfs_result:
        for frame in resultado.dfs_result.values():
            texto += frame.to_json(force_ascii=False)
    texto += f" {resultado.stdout or ''} {resultado.error or ''}"
    return Observacao(
        sucesso=bool(resultado.success),
        erro=str(resultado.error or ""),
        texto_resultante=texto,
    )


def _assert_nao_vazou(observacao: Observacao) -> None:
    """Nenhum segredo, usuário do sistema ou conteúdo de arquivo do SO na saída."""
    assert SEGREDO not in observacao.texto_resultante, "o segredo do ambiente vazou"
    assert "PROBE_SECRET" not in observacao.texto_resultante, "nome do segredo vazou"


# ---------------------------------------------------------------------------------------
# 1. Exfiltração de segredos e ambiente
# ---------------------------------------------------------------------------------------


class TestExfiltracaoDeAmbiente:
    """O vetor mais grave da versão anterior: chave de API lida de dentro do sandbox."""

    def test_os_environ_via_pandas_nao_expoe_segredo(self, executor, df):
        obs = _observar(
            executor,
            "df_result = df.assign(v=str(pd.io.common.os.environ.get('PROBE_SECRET')))",
            df,
        )
        _assert_nao_vazou(obs)
        assert SEGREDO not in obs.texto_resultante

    def test_ambiente_do_filho_esta_vazio(self, executor, df):
        """Mesmo se alcançar o módulo os, não há nada para ler."""
        obs = _observar(
            executor,
            "import os\ndf_result = df.assign(v=str(dict(os.environ)))",
            df,
        )
        _assert_nao_vazou(obs)

    def test_getenv_bloqueado(self, executor, df):
        obs = _observar(executor, "df_result = df.assign(v=str(pd.get_option('x')))", df)
        _assert_nao_vazou(obs)

    def test_variaveis_do_ambiente_do_processo_pai_nao_cruzam(self, executor, df, monkeypatch):
        monkeypatch.setenv("OUTRO_SEGREDO_PAI", "valor-super-secreto-pai")
        obs = _observar(
            executor,
            "df_result = df.assign(v=str(pd.io.common.os.environ))",
            df,
        )
        assert "valor-super-secreto-pai" not in obs.texto_resultante


# ---------------------------------------------------------------------------------------
# 2. Execução de código e de processos
# ---------------------------------------------------------------------------------------


class TestExecucaoDeProcessos:
    """RCE: o achado crítico da versão anterior (`pd.io.common.os.popen`)."""

    @pytest.mark.parametrize(
        "codigo",
        [
            "df_result = df.assign(v=pd.io.common.os.popen('whoami').read())",
            "df_result = df.assign(v=str(pd.io.common.os.system('whoami')))",
            "df_result = df.assign(v=str(pd.io.common.subprocess.run(['whoami'])))",
            "df_result = df.assign(v=str(__import__('os').popen('whoami').read()))",
            "df_result = df.assign(v=eval('__import__(\"os\").getcwd()'))",
            "exec('import os')\ndf_result = df",
            "df_result = df.assign(v=str(compile('1', 'x', 'eval')))",
        ],
    )
    def test_popen_system_e_afins_nao_executam(self, executor, df, codigo):
        obs = _observar(executor, codigo, df)
        _assert_nao_vazou(obs)
        if USUARIO:
            assert USUARIO.lower() not in obs.texto_resultante.lower(), (
                "saída de comando do SO apareceu no resultado"
            )
        assert "nt authority" not in obs.texto_resultante.lower()

    def test_escalada_por_subclasses_bloqueada(self, executor, df):
        obs = _observar(
            executor,
            "df_result = df.assign(v=str(object.__subclasses__()))",
            df,
        )
        assert obs.sucesso is False

    def test_escalada_por_format_string_bloqueada(self, executor, df):
        """`str.format` alcança atributos internos sem usar ponto no código-fonte.

        Sem proteção, `'{0.__class__.__bases__[0].__subclasses__}'.format(df)` devolve a lista
        de subclasses de `object` — a porta de entrada para chegar a `os`/`subprocess`.
        O critério aqui é o método NÃO ter sido resolvido (o texto da mensagem de bloqueio
        pode citar o trecho recusado, então não serve como verificação).
        """
        obs = _observar(
            executor,
            "df_result = df.assign(v='{0.__class__.__bases__[0].__subclasses__}'.format(df))",
            df,
        )
        assert obs.sucesso is False
        assert "built-in method __subclasses__" not in obs.texto_resultante
        assert "class 'type'" not in obs.texto_resultante

    def test_escalada_por_format_string_com_chave(self, executor, df):
        """Variante por chave nomeada, que não passa por índice posicional."""
        obs = _observar(
            executor,
            "df_result = df.assign(v='{x.__class__.__subclasses__}'.format(x=object))",
            df,
        )
        assert obs.sucesso is False
        assert "built-in method" not in obs.texto_resultante

    def test_format_string_nao_permite_invocar_metodo_alcancado(self, executor, df):
        """Mesmo se a string vazasse, o método não pode ser obtido para ser chamado."""
        obs = _observar(
            executor,
            "f = '{0.__subclasses__}'.format(df)\ndf_result = df.assign(v=str(f()))",
            df,
        )
        assert obs.sucesso is False
        assert "class 'type'" not in obs.texto_resultante

    def test_format_legitimo_continua_funcionando(self, executor, df):
        """A proteção não pode quebrar formatação normal, que é uso legítimo e comum."""
        obs = _observar(
            executor,
            "df_result = df.assign(v=['{0}: {1} itens'.format('total', len(df))] * len(df))",
            df,
        )
        assert obs.sucesso is True, obs.erro
        assert "total: 2 itens" in obs.texto_resultante

    def test_fstring_continua_funcionando(self, executor, df):
        obs = _observar(
            executor,
            "rotulo = f'linhas={len(df)}'\ndf_result = df.assign(v=[rotulo] * len(df))",
            df,
        )
        assert obs.sucesso is True, obs.erro
        assert "linhas=2" in obs.texto_resultante

    def test_format_com_especificacao_de_formato(self, executor, df):
        obs = _observar(
            executor,
            "df_result = df.assign(v=[format(12.345, '.2f') + '%'] * len(df))",
            df,
        )
        assert obs.sucesso is True, obs.erro
        assert "12.35%" in obs.texto_resultante

    def test_format_map_bloqueado(self, executor, df):
        """`format_map` aceita mapeamento arbitrário — vetor de traversal."""
        obs = _observar(
            executor,
            "df_result = df.assign(v=['{x.__class__}'.format_map({'x': df})] * len(df))",
            df,
        )
        assert obs.sucesso is False

    def test_ctypes_bloqueado(self, executor, df):
        obs = _observar(executor, "import ctypes\ndf_result = df", df)
        assert obs.sucesso is False

    def test_lambda_e_closure_nao_escapam(self, executor, df):
        obs = _observar(
            executor,
            "f = lambda: pd.io.common.os.getcwd()\ndf_result = df.assign(v=f())",
            df,
        )
        _assert_nao_vazou(obs)


# ---------------------------------------------------------------------------------------
# 3. Rede
# ---------------------------------------------------------------------------------------


class TestRede:
    """Sem egresso não existe canal de exfiltração."""

    @pytest.mark.parametrize(
        "codigo",
        [
            "import socket\ndf_result = df",
            "import urllib.request\ndf_result = df",
            "import http.client\ndf_result = df",
            "df_result = df.assign(v=str(pd.io.common.os.getcwd()))",
        ],
    )
    def test_imports_de_rede_bloqueados(self, executor, df, codigo):
        obs = _observar(executor, codigo, df)
        _assert_nao_vazou(obs)

    def test_socket_nao_pode_ser_criado(self, executor, df):
        obs = _observar(
            executor,
            "s = pd.io.common.importlib.import_module('socket').socket()\ndf_result = df",
            df,
        )
        assert obs.sucesso is False


# ---------------------------------------------------------------------------------------
# 4. Sistema de arquivos
# ---------------------------------------------------------------------------------------


class TestSistemaDeArquivos:
    """Leitura arbitrária e escrita/remoção: bloqueadas e verificadas no disco real."""

    def test_leitura_de_arquivo_do_sistema_bloqueada(self, executor, df):
        obs = _observar(executor, "df_result = pd.read_csv('C:/Windows/win.ini')", df)
        assert obs.sucesso is False
        assert "[fonts]" not in obs.texto_resultante.lower()

    def test_open_direto_bloqueado(self, executor, df):
        obs = _observar(
            executor,
            "df_result = df.assign(v=open('C:/Windows/win.ini').read())",
            df,
        )
        assert obs.sucesso is False

    def test_escrita_em_disco_nao_acontece(self, executor, df, tmp_path, monkeypatch):
        """O critério é o arquivo NÃO existir, não a mensagem de erro."""
        monkeypatch.chdir(tmp_path)
        alvo = Path("evil.csv")
        obs = _observar(executor, "df.to_csv('evil.csv')\ndf_result = df", df)
        assert obs.sucesso is False
        assert not alvo.exists(), "o sandbox escreveu um arquivo no diretório de trabalho"
        assert not (tmp_path / "evil.xlsx").exists()

    def test_escrita_com_caminho_absoluto_nao_acontece(self, executor, df, tmp_path):
        alvo = tmp_path / "abs_evil.csv"
        codigo = f"df.to_csv({str(alvo)!r})\ndf_result = df"
        obs = _observar(executor, codigo, df)
        assert obs.sucesso is False
        assert not alvo.exists()

    def test_remocao_de_arquivo_nao_acontece(self, executor, df, tmp_path):
        vitima = tmp_path / "importante.txt"
        vitima.write_text("dados do usuario", encoding="utf-8")
        codigo = f"pd.io.common.os.remove({str(vitima)!r})\ndf_result = df"
        obs = _observar(executor, codigo, df)
        assert obs.sucesso is False
        assert vitima.exists(), "o sandbox removeu um arquivo do usuário"

    def test_leitura_arbitraria_do_diretorio_do_projeto_bloqueada(self, executor, df):
        obs = _observar(executor, "df_result = df.assign(v=str(pd.io.common.os.listdir('.')))", df)
        _assert_nao_vazou(obs)
        assert ".gitignore" not in obs.texto_resultante

    def test_pickle_load_nao_le_arquivo(self, executor, df, tmp_path):
        alvo = tmp_path / "payload.pkl"
        alvo.write_bytes(b"cotorra")
        codigo = f"df_result = pd.read_pickle({str(alvo)!r})"
        obs = _observar(executor, codigo, df)
        assert obs.sucesso is False


# ---------------------------------------------------------------------------------------
# 5. Robustez do próprio sandbox
# ---------------------------------------------------------------------------------------


class TestRobustez:
    """O sandbox precisa aguentar abuso sem cair nem travar o processo da aplicação."""

    def test_laco_infinito_e_interrompido(self, df):
        from src.engine.code_executor import SandboxLimits

        executor = SafeCodeExecutor(SandboxLimits(wall_timeout_seconds=6, cpu_seconds=4))
        obs = _observar(executor, "while True:\n    pass", df)
        assert obs.sucesso is False

    def test_consumo_de_memoria_tem_limite_de_celulas(self, df):
        from src.engine.code_executor import SandboxLimits

        executor = SafeCodeExecutor(SandboxLimits(max_cells=1))
        obs = _observar(executor, "df_result = df", df)
        assert obs.sucesso is False

    def test_processo_da_aplicacao_sobrevive_a_falha_do_filho(self, executor, df):
        """Um erro catastrófico no filho não pode derrubar o processo que hospeda o app."""
        obs = _observar(executor, "raise SystemExit(1)", df)
        assert obs.sucesso is False
        # ...e o executor continua utilizável na chamada seguinte
        obs2 = _observar(executor, "df_result = df", df)
        assert obs2.sucesso is True

    def test_saida_gigante_nao_estoura_memoria(self, executor, df):
        obs = _observar(
            executor,
            "print('x' * 1000000)\ndf_result = df",
            df,
        )
        assert obs.sucesso is True  # stdout truncado, mas execução válida

    def test_sem_definicao_de_df_result_devolve_erro_claro(self, executor, df):
        obs = _observar(executor, "x = 1", df)
        assert obs.sucesso is False

    def test_entradas_do_sandbox_nao_podem_ser_sobrescritas(self, executor, df):
        for alvo in ("pd", "np", "dfs", "df"):
            obs = _observar(executor, f"{alvo} = 1\ndf_result = df", df)
            assert obs.sucesso is False, f"{alvo} nao deveria poder ser reatribuido"

    def test_modulo_os_nao_esta_no_escopo(self, executor, df):
        obs = _observar(executor, "df_result = df.assign(v=str(os.getcwd()))", df)
        assert obs.sucesso is False
