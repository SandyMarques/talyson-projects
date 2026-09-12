"""Testes da lógica de estado da aplicação (`app._mesclar_resultado`).

Regressão coberta: um `dfs_result` parcial (a IA alterou só uma aba) substituía o workbook
INTEIRO. As abas não mencionadas desapareciam da tela, do histórico e do `.xlsx` exportado, sem
nenhum aviso ao usuário.

`_mesclar_resultado` foi extraída como função pura justamente para ser testável sem precisar
subir o runtime do Streamlit (Humble Object: a lógica sai do componente acoplado à UI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from app import _mesclar_resultado


@dataclass
class ResultadoFake:
    """Stub de `PipelineResult`: só os campos que a mesclagem consome."""

    success: bool = True
    final_df: Optional[pd.DataFrame] = None
    final_dfs: Optional[Dict[str, pd.DataFrame]] = None


def _abas_tres() -> Dict[str, pd.DataFrame]:
    return {
        "Vendas": pd.DataFrame({"ID": [1, 2], "Valor": [10, 20]}),
        "Clientes": pd.DataFrame({"ID": [1, 2], "Nome": ["Ana", "Bob"]}),
        "Produtos": pd.DataFrame({"ID": [1], "Nome": ["Caneta"]}),
    }


class TestPreservacaoDeAbas:
    def test_aba_nao_mencionada_e_preservada(self):
        anteriores = _abas_tres()
        novo = pd.DataFrame({"ID": [1], "Total": [30]})
        abas, preservadas = _mesclar_resultado(anteriores, ResultadoFake(final_dfs={"Vendas": novo}))

        assert set(abas.keys()) == {"Vendas", "Clientes", "Produtos"}
        assert sorted(preservadas) == ["Clientes", "Produtos"]
        assert list(abas["Vendas"].columns) == ["ID", "Total"]
        assert "Nome" in abas["Clientes"].columns

    def test_todas_as_abas_mencionadas_nao_gera_preservadas(self):
        anteriores = _abas_tres()
        abas, preservadas = _mesclar_resultado(
            anteriores,
            ResultadoFake(final_dfs={k: v.copy() for k, v in anteriores.items()}),
        )
        assert preservadas == []
        assert set(abas.keys()) == set(anteriores.keys())

    def test_resultado_unico_usa_resultado(self):
        abas, preservadas = _mesclar_resultado(
            _abas_tres(), ResultadoFake(final_df=pd.DataFrame({"X": [1]}))
        )
        assert list(abas.keys()) == ["Resultado"]
        assert preservadas == []

    def test_aba_nova_e_adicionada_sem_descartar_as_antigas(self):
        abas, preservadas = _mesclar_resultado(
            _abas_tres(),
            ResultadoFake(final_dfs={"Resumo": pd.DataFrame({"T": [5]})}),
        )
        assert set(abas.keys()) == {"Vendas", "Clientes", "Produtos", "Resumo"}
        assert sorted(preservadas) == ["Clientes", "Produtos", "Vendas"]

    def test_falha_devolve_estado_intacto(self):
        anteriores = _abas_tres()
        abas, preservadas = _mesclar_resultado(
            anteriores, ResultadoFake(success=False, final_df=pd.DataFrame({"X": [1]}))
        )
        assert set(abas.keys()) == set(anteriores.keys())
        assert preservadas == []

    def test_sem_resultado_nem_df_mantem_abas(self):
        anteriores = _abas_tres()
        abas, preservadas = _mesclar_resultado(anteriores, ResultadoFake())
        assert set(abas.keys()) == set(anteriores.keys())
        assert preservadas == []

    def test_estado_anterior_nao_e_mutado(self):
        anteriores = _abas_tres()
        del anteriores["Produtos"]  # sanity: garantir que a função trabalha com o que recebe
        antes = set(anteriores.keys())
        abas, _ = _mesclar_resultado(
            anteriores, ResultadoFake(final_dfs={"Vendas": pd.DataFrame({"A": [1]})})
        )
        assert set(anteriores.keys()) == antes
        assert "Produtos" not in abas

    def test_workbook_de_uma_aba(self):
        anteriores = {"Unica": pd.DataFrame({"A": [1]})}
        abas, preservadas = _mesclar_resultado(
            anteriores, ResultadoFake(final_dfs={"Unica": pd.DataFrame({"A": [2]})})
        )
        assert set(abas.keys()) == {"Unica"}
        assert preservadas == []
