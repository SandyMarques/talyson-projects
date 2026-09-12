"""Testes para o manipulador de arquivos (FileHandler) com suporte multi-abas.

Inclui regressão de bugs confirmados: CSV com vírgula dentro de campo entre aspas (a heurística
de contagem de substring escolhia o delimitador errado), `.xls` aceito mas impossível de ler,
e perda silenciosa de linhas malformadas.
"""

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


# ---------------------------------------------------------------------------------------
# Robustez de leitura: casos que a heurística de contagem de substring errava
# ---------------------------------------------------------------------------------------


class TestDeteccaoDeDelimitador:
    """Detecção de delimitador precisa respeitar aspas, não contar substrings."""

    def test_csv_ponto_virgula_com_virgula_entre_aspas(self):
        """Caso real: endereços com vírgula dentro de campos entre aspas."""
        conteudo = (
            'Nome;Endereco;Cidade\n'
            'Ana;"Rua A, 100, apto 2";Sao Paulo\n'
            'Bruno;"Av. B, 2000";Rio de Janeiro\n'
        )
        df, meta = FileHandler.load_csv(conteudo.encode("utf-8"))
        assert list(df.columns) == ["Nome", "Endereco", "Cidade"]
        assert meta["delimiter"] == ";"
        assert df.loc[0, "Endereco"] == "Rua A, 100, apto 2"

    def test_csv_virgula_com_ponto_virgula_no_texto(self):
        conteudo = 'Nome,Observacao\nAna,"gosta de a;b"\nBruno,"x;y"\n'
        df, meta = FileHandler.load_csv(conteudo.encode("utf-8"))
        assert list(df.columns) == ["Nome", "Observacao"]
        assert meta["delimiter"] == ","

    def test_csv_tab(self):
        conteudo = "A\tB\tC\n1\t2\t3\n"
        df, meta = FileHandler.load_csv(conteudo.encode("utf-8"))
        assert list(df.columns) == ["A", "B", "C"]
        assert meta["delimiter"] == "\t"

    def test_csv_encoding_latin1(self):
        conteudo = "Cidade;Habitantes\nSão Paulo;12000000\n"
        df, meta = FileHandler.load_csv(conteudo.encode("latin-1"))
        assert len(df) == 1
        assert "Habitantes" in df.columns


class TestVolumeEFormatos:
    """Limites e formatos precisam falhar de forma explícita, não obscura."""

    def test_xls_legado_recusado_com_mensagem_clara(self):
        with pytest.raises(ValueError, match="não é suportado"):
            FileHandler.load_all_sheets(b"conteudo binario", "planilha.xls")

    def test_formato_desconhecido_recusado(self):
        with pytest.raises(ValueError, match="não suportado"):
            FileHandler.load_all_sheets(b"abc", "arquivo.txt")

    def test_csv_vazio_recusado(self):
        with pytest.raises(ValueError, match="vazio"):
            FileHandler.load_csv(b"")

    def test_limite_de_linhas_no_upload(self, monkeypatch):
        """Planilha gigante deve ser recusada antes de consumir memória."""
        from src.core import config as config_module

        monkeypatch.setattr(config_module.config, "max_upload_rows", 5)
        conteudo = "A,B\n" + "\n".join(f"{i},{i}" for i in range(50))
        with pytest.raises(ValueError, match="acima do limite"):
            FileHandler.load_all_sheets(conteudo.encode("utf-8"), "grande.csv")

    def test_limite_de_colunas_no_upload(self, monkeypatch):
        from src.core import config as config_module

        monkeypatch.setattr(config_module.config, "max_upload_columns", 3)
        df = pd.DataFrame({f"c{i}": [1] for i in range(10)})
        excel_bytes = FileHandler.export_to_excel_bytes(df)
        with pytest.raises(ValueError, match="colunas"):
            FileHandler.load_all_sheets(excel_bytes, "larga.xlsx")

    def test_linhas_malformadas_sao_reportadas(self):
        """`on_bad_lines='skip'` não pode perder dados em silêncio."""
        conteudo = 'A,B\n1,2\n3,4,5,6,7\n5,6\n'
        df, meta = FileHandler.load_csv(conteudo.encode("utf-8"))
        assert "aviso" in meta
        assert "linhas_descartadas" in meta
