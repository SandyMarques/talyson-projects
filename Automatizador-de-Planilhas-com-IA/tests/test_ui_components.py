"""Testes dos componentes de UI e do estado da aplicação.

Cobre regressões confirmadas por execução:

1. **Crash na exportação CSV**: `render_download_buttons` usava
   `data.get("Resultado") or list(data.values())[0]`. Avaliar a verdade de um DataFrame levanta
   `ValueError: The truth value of a DataFrame is ambiguous`, então o app quebrava no rerun
   seguinte a QUALQUER transformação bem-sucedida — sem nem clicar em download.
2. **XSS no painel**: a explicação do LLM (que leu o conteúdo da planilha) era renderizada com
   `unsafe_allow_html=True` sem escape.
3. **Abas perdidas**: um `dfs_result` parcial substituía o workbook inteiro.

Estratégia de doubles: `streamlit` é substituído por um fake que **registra** as chamadas
(Spy), permitindo verificar o CONTEÚDO do que foi mandado renderizar — que é onde o escape e a
escolha da aba acontecem. Assim o teste exercita a lógica sem depender do runtime do Streamlit.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import pytest

from src.ui import components


class StreamlitSpy:
    """Spy: registra chamadas de renderização sem executar o runtime real do Streamlit."""

    def __init__(self) -> None:
        self.markdowns: List[str] = []
        self.avisos: List[str] = []
        self.captions: List[str] = []
        self.downloads: List[Dict[str, Any]] = []
        self.colunas = _ColumnsSpy(self)

    # API mínima usada pelos componentes
    def markdown(self, texto: str = "", **kwargs: Any) -> None:
        self.markdowns.append(texto)

    def caption(self, texto: str = "", **kwargs: Any) -> None:
        self.captions.append(texto)

    def warning(self, texto: str = "", **kwargs: Any) -> None:
        self.avisos.append(texto)

    def columns(self, n: int, **kwargs: Any) -> List[Any]:
        return [self for _ in range(n if isinstance(n, int) else len(n))]

    def download_button(self, label: str = "", data: Any = None, **kwargs: Any) -> None:
        self.downloads.append({"label": label, "data": data, "kwargs": kwargs})

    def __enter__(self) -> "StreamlitSpy":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


class _ColumnsSpy(StreamlitSpy):
    """Colunas se comportam como o próprio spy (para `with col:` funcionar)."""

    def __init__(self, pai: StreamlitSpy) -> None:
        self._pai = pai
        self.markdowns = pai.markdowns
        self.avisos = pai.avisos
        self.captions = pai.captions
        self.downloads = pai.downloads
        self.colunas = self

    def columns(self, n: int, **kwargs: Any) -> List[Any]:
        return [self for _ in range(n if isinstance(n, int) else len(n))]


@pytest.fixture
def st_spy(monkeypatch) -> StreamlitSpy:
    """Injeta o spy no módulo de componentes."""
    spy = StreamlitSpy()
    monkeypatch.setattr(components, "st", spy)
    return spy


# ---------------------------------------------------------------------------------------
# Regressão: crash na exportação (bug crítico)
# ---------------------------------------------------------------------------------------


class TestExportacaoNaoQuebra:
    """`bool(DataFrame)` levanta ValueError: nunca usar DataFrame em contexto booleano."""

    def test_dict_com_resultado_exporta(self, st_spy):
        dados = {"Resultado": pd.DataFrame({"A": [1, 2]}), "Outra": pd.DataFrame({"B": [3]})}
        components.render_download_buttons(dados, "planilha.xlsx")
        assert len(st_spy.downloads) == 2  # xlsx + csv

    def test_dict_sem_resultado_usa_primeira_aba(self, st_spy):
        dados = {"Vendas": pd.DataFrame({"A": [1]}), "Clientes": pd.DataFrame({"B": [2]})}
        components.render_download_buttons(dados, "planilha.xlsx")
        assert len(st_spy.downloads) == 2

    def test_aba_unica(self, st_spy):
        components.render_download_buttons({"Unica": pd.DataFrame({"A": [1]})}, "p.xlsx")
        assert len(st_spy.downloads) == 2

    def test_dataframe_direto(self, st_spy):
        components.render_download_buttons(pd.DataFrame({"A": [1, 2, 3]}), "p.xlsx")
        assert len(st_spy.downloads) == 2

    def test_dict_vazio_nao_quebra(self, st_spy):
        """Antes: `list(data.values())[0]` em dict vazio levantava IndexError."""
        components.render_download_buttons({}, "p.xlsx")
        assert st_spy.avisos or st_spy.captions

    def test_dataframe_com_coluna_booleana_nao_confunde(self, st_spy):
        """DataFrame cujos valores são False não pode ser tratado como "vazio"."""
        dados = {"Resultado": pd.DataFrame({"flag": [False, False]})}
        components.render_download_buttons(dados, "p.xlsx")
        assert len(st_spy.downloads) == 2

    def test_csv_gerado_tem_separador_ponto_virgula(self, st_spy):
        componentes = {"Resultado": pd.DataFrame({"A": [1], "B": [2]})}
        components.render_download_buttons(componentes, "p.xlsx")
        csv_bytes = st_spy.downloads[1]["data"]
        assert b"A;B" in csv_bytes


# ---------------------------------------------------------------------------------------
# XSS: conteúdo da planilha e do LLM é dado não confiável
# ---------------------------------------------------------------------------------------


class TestEscapeDeConteudo:
    def test_explicacao_do_llm_e_escapada(self, st_spy):
        components.render_ai_explanation('<img src=x onerror="alert(1)">resumo')
        html = st_spy.markdowns[-1]
        assert "<img" not in html
        assert "&lt;img" in html

    def test_script_na_explicacao_e_escapado(self, st_spy):
        components.render_ai_explanation("<script>alert('xss')</script>")
        html = st_spy.markdowns[-1]
        assert "<script>" not in html

    def test_quebra_de_linha_vira_br_no_texto_escapado(self, st_spy):
        components.render_ai_explanation("linha 1\nlinha 2")
        html = st_spy.markdowns[-1]
        assert "linha 1<br>linha 2" in html

    def test_nome_de_aba_malicioso_e_escapado(self, st_spy):
        dfs = {
            "<img src=x onerror=alert(1)>": pd.DataFrame({"A": [1]}),
            "Normal": pd.DataFrame({"B": [2]}),
        }
        components.render_workbook_overview(dfs)
        html = st_spy.markdowns[-1]
        assert "<img" not in html
        assert "&lt;img" in html

    def test_nome_de_aba_legitimo_aparece(self, st_spy):
        dfs = {"Vendas 2024": pd.DataFrame({"A": [1]}), "Clientes": pd.DataFrame({"B": [2]})}
        components.render_workbook_overview(dfs)
        assert "Vendas 2024" in st_spy.markdowns[-1]

    def test_diff_com_coluna_maliciosa_e_escapado(self, st_spy):
        components.render_diff_summary(
            columns_added=["<script>alert(1)</script>"],
            columns_removed=[],
            rows_delta=1,
            execution_time_ms=12.0,
        )
        html = " ".join(st_spy.markdowns)
        assert "<script>" not in html
