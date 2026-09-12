"""Manipulador de arquivos para leitura e exportação de CSV e XLSX (multi-abas).

Robustez tratada aqui:
- **Detecção de delimitador consciente de aspas** (`csv.Sniffer`), em vez de contar ocorrências
  de substring no texto cru — com contagem ingênua, uma vírgula dentro de um campo entre aspas
  vencia a votação e quebrava o parse de um CSV separado por ponto e vírgula.
- **Limite de volume** no upload (linhas/colunas) para não estourar a memória do processo.
- **Aviso explícito de linhas descartadas**: `on_bad_lines="skip"` não pode ser silencioso.
- **Recusa clara de `.xls` legado**, que o engine openpyxl não lê (antes dava erro obscuro).
"""

import csv
import io
from typing import Dict, List, Optional, Tuple, Union

import pandas as pd

from src.core.config import config


class FileHandler:
    """Carrega e exporta planilhas com robustez e suporte multi-abas."""

    SUPPORTED_ENCODINGS = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]
    SUPPORTED_DELIMITERS = [",", ";", "\t", "|"]

    #: Formato moderno de Excel, lido pelo openpyxl.
    XLSX_EXTENSIONS = (".xlsx", ".xlsm")
    #: Formato binário legado do Excel: exige xlrd, que não é dependência do projeto.
    XLS_LEGADO_EXTENSIONS = (".xls",)

    @classmethod
    def load_all_sheets(
        cls,
        file_input: Union[str, io.BytesIO, io.StringIO, bytes],
        filename: str,
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, any]]:
        """
        Carrega todas as abas de um arquivo Excel ou um CSV como dicionário de DataFrames.
        Retorna (Dict[nome_aba, DataFrame], metadados).
        """
        lower_name = filename.lower()
        if lower_name.endswith(cls.XLS_LEGADO_EXTENSIONS):
            raise ValueError(
                "O formato .xls (Excel 97-2003) não é suportado. "
                "Abra o arquivo no Excel/LibreOffice e salve como .xlsx."
            )
        if lower_name.endswith(cls.XLSX_EXTENSIONS):
            return cls.load_excel_all_sheets(file_input)
        if lower_name.endswith(".csv"):
            df, meta = cls.load_csv(file_input)
            meta["sheets"] = ["Planilha"]
            cls._validar_volume({"Planilha": df})
            return {"Planilha": df}, meta
        raise ValueError(
            f"Formato de arquivo não suportado: {filename}. Utilize .csv ou .xlsx."
        )

    @classmethod
    def load_file(
        cls,
        file_input: Union[str, io.BytesIO, io.StringIO, bytes],
        filename: str,
        sheet_name: Optional[Union[str, int]] = 0,
    ) -> Tuple[pd.DataFrame, Dict[str, any]]:
        """Carrega um arquivo CSV ou aba específica de XLSX para DataFrame único."""
        lower_name = filename.lower()
        if lower_name.endswith(cls.XLS_LEGADO_EXTENSIONS):
            raise ValueError(
                "O formato .xls (Excel 97-2003) não é suportado. Salve como .xlsx."
            )
        if lower_name.endswith(cls.XLSX_EXTENSIONS):
            return cls.load_excel(file_input, sheet_name=sheet_name)
        if lower_name.endswith(".csv"):
            return cls.load_csv(file_input)
        raise ValueError(
            f"Formato de arquivo não suportado: {filename}. Utilize .csv ou .xlsx."
        )

    @classmethod
    def _validar_volume(cls, dfs: Dict[str, pd.DataFrame]) -> None:
        """Recusa workbooks acima do limite configurado (proteção de memória)."""
        total_linhas = sum(len(df) for df in dfs.values())
        if total_linhas > config.max_upload_rows:
            raise ValueError(
                f"O arquivo tem {total_linhas} linhas, acima do limite de "
                f"{config.max_upload_rows}. Filtre ou divida a planilha antes de carregar."
            )
        maiores = max((len(df.columns) for df in dfs.values()), default=0)
        if maiores > config.max_upload_columns:
            raise ValueError(
                f"Uma das abas tem {maiores} colunas, acima do limite de "
                f"{config.max_upload_columns}."
            )
        vazias = [nome for nome, df in dfs.items() if df.empty and len(df.columns) == 0]
        if vazias and len(vazias) == len(dfs):
            raise ValueError("O arquivo não contém nenhuma aba com dados legíveis.")

    @classmethod
    def get_excel_sheets(cls, file_input: Union[str, io.BytesIO, bytes]) -> List[str]:
        """Obtém a lista de abas disponíveis no arquivo Excel."""
        if isinstance(file_input, bytes):
            file_input = io.BytesIO(file_input)
        with pd.ExcelFile(file_input, engine="openpyxl") as excel_file:
            return list(excel_file.sheet_names)

    @classmethod
    def load_excel_all_sheets(
        cls,
        file_input: Union[str, io.BytesIO, bytes],
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, any]]:
        """Carrega todas as abas de uma planilha Excel em um dicionário {nome_aba: DataFrame}."""
        if isinstance(file_input, bytes):
            file_input = io.BytesIO(file_input)

        if hasattr(file_input, "seek"):
            file_input.seek(0)

        dict_dfs = pd.read_excel(file_input, sheet_name=None, engine="openpyxl")
        # Abas totalmente vazias não têm valor e quebram cálculos de métricas.
        dict_dfs = {nome: df for nome, df in dict_dfs.items() if not (df.empty and not len(df.columns))}
        if not dict_dfs:
            raise ValueError("Nenhuma aba com dados foi encontrada no arquivo Excel.")

        cls._validar_volume(dict_dfs)

        sheets = list(dict_dfs.keys())
        metadata = {
            "format": "excel",
            "sheets": sheets,
            "total_sheets": len(sheets),
            "total_rows": sum(len(df) for df in dict_dfs.values()),
        }
        return dict_dfs, metadata

    @classmethod
    def load_excel(
        cls,
        file_input: Union[str, io.BytesIO, bytes],
        sheet_name: Optional[Union[str, int]] = 0,
    ) -> Tuple[pd.DataFrame, Dict[str, any]]:
        """Carrega uma planilha Excel específica."""
        if isinstance(file_input, bytes):
            file_input = io.BytesIO(file_input)

        if hasattr(file_input, "seek"):
            file_input.seek(0)

        sheets = cls.get_excel_sheets(file_input)
        
        if hasattr(file_input, "seek"):
            file_input.seek(0)

        target_sheet = sheet_name if sheet_name is not None else 0
        df = pd.read_excel(file_input, sheet_name=target_sheet, engine="openpyxl")
        
        metadata = {
            "format": "excel",
            "sheets": sheets,
            "selected_sheet": target_sheet,
            "rows": len(df),
            "columns": len(df.columns),
        }
        return df, metadata

    @classmethod
    def _detectar_delimitador(cls, amostra: str) -> Optional[str]:
        """Detecta o delimitador respeitando aspas.

        A heurística anterior contava ocorrências de substring no texto cru: em um CSV separado
        por `;` com campos como `"Rua A, 100"`, a vírgula ganhava a votação e o parse quebrava.
        `csv.Sniffer` entende o quoting.
        """
        try:
            return csv.Sniffer().sniff(amostra, delimiters="".join(cls.SUPPORTED_DELIMITERS)).delimiter
        except csv.Error:
            pass

        # Fallback determinístico: escolhe o delimitador com contagem consistente por linha.
        linhas = [linha for linha in amostra.splitlines() if linha.strip()][:20]
        if not linhas:
            return None
        melhor, melhor_pontuacao = None, -1.0
        for delimitador in cls.SUPPORTED_DELIMITERS:
            contagens = [linha.count(delimitador) for linha in linhas]
            if not contagens or max(contagens) == 0:
                continue
            # Consistência importa mais que volume: um delimitador real aparece o mesmo
            # número de vezes em todas as linhas.
            moda = max(set(contagens), key=contagens.count)
            consistencia = contagens.count(moda) / len(contagens)
            pontuacao = consistencia * 10 + moda
            if pontuacao > melhor_pontuacao:
                melhor, melhor_pontuacao = delimitador, pontuacao
        return melhor

    @classmethod
    def load_csv(
        cls,
        file_input: Union[str, io.BytesIO, io.StringIO, bytes],
    ) -> Tuple[pd.DataFrame, Dict[str, any]]:
        """
        Carrega um arquivo CSV tentando diferentes encodings e delimitadores automaticamente.
        """
        raw_bytes: bytes = b""
        if isinstance(file_input, str):
            with open(file_input, "rb") as f:
                raw_bytes = f.read()
        elif isinstance(file_input, bytes):
            raw_bytes = file_input
        elif hasattr(file_input, "read"):
            if hasattr(file_input, "seek"):
                file_input.seek(0)
            data = file_input.read()
            raw_bytes = data if isinstance(data, bytes) else data.encode("utf-8")
            if hasattr(file_input, "seek"):
                file_input.seek(0)

        if not raw_bytes:
            raise ValueError("O arquivo CSV está vazio.")

        last_error = None
        for encoding in cls.SUPPORTED_ENCODINGS:
            try:
                decoded_sample = raw_bytes[:8192].decode(encoding)
            except UnicodeDecodeError:
                continue

            delimitador = cls._detectar_delimitador(decoded_sample) or ","
            try:
                stream = io.BytesIO(raw_bytes)
                df, descartadas = cls._ler_csv_contando_descartes(stream, encoding, delimitador)

                if len(df.columns) == 1:
                    # Pode ser um CSV de coluna única de verdade, ou delimitador errado.
                    for alternativo in [d for d in cls.SUPPORTED_DELIMITERS if d != delimitador]:
                        stream.seek(0)
                        df_alt, descartadas_alt = cls._ler_csv_contando_descartes(
                            stream, encoding, alternativo
                        )
                        if len(df_alt.columns) > 1:
                            df, descartadas, delimitador = df_alt, descartadas_alt, alternativo
                            break

                metadata = {
                    "format": "csv",
                    "encoding": encoding,
                    "delimiter": delimitador,
                    "rows": len(df),
                    "columns": len(df.columns),
                    "sheets": ["Planilha"],
                    "linhas_descartadas": descartadas,
                    "aviso": (
                        f"{descartadas} linha(s) malformada(s) foram descartadas na leitura."
                        if descartadas
                        else None
                    ),
                }
                return df, metadata
            except Exception as e:  # noqa: BLE001 - tenta o próximo encoding
                last_error = e
                continue

        try:
            stream = io.BytesIO(raw_bytes)
            df, descartadas = cls._ler_csv_contando_descartes(stream, None, None)
            return df, {
                "format": "csv",
                "encoding": "auto-fallback",
                "delimiter": "auto",
                "rows": len(df),
                "columns": len(df.columns),
                "sheets": ["Planilha"],
                "linhas_descartadas": descartadas,
                "aviso": (
                    f"{descartadas} linha(s) malformada(s) foram descartadas na leitura."
                    if descartadas
                    else None
                ),
            }
        except Exception as fallback_error:  # noqa: BLE001
            raise ValueError(
                f"Não foi possível decodificar o arquivo CSV: {last_error or fallback_error}"
            ) from fallback_error

    @staticmethod
    def _ler_csv_contando_descartes(
        stream: io.BytesIO,
        encoding: Optional[str],
        delimitador: Optional[str],
    ) -> Tuple[pd.DataFrame, int]:
        """Lê o CSV com `on_bad_lines='skip'` e informa quantas linhas foram descartadas.

        O modo silencioso perdia dados sem o usuário saber; agora a contagem vai nos metadados.
        """
        kwargs: Dict[str, any] = {"on_bad_lines": "skip"}
        if encoding:
            kwargs["encoding"] = encoding
        if delimitador:
            kwargs["sep"] = delimitador
        else:
            kwargs["sep"] = None
            kwargs["engine"] = "python"

        stream.seek(0)
        df = pd.read_csv(stream, **kwargs)

        # Segunda passada estrita só para contar: barato e dá visibilidade real da perda.
        descartadas = 0
        try:
            stream.seek(0)
            kwargs_estrito = {**kwargs, "on_bad_lines": "error"}
            pd.read_csv(stream, **kwargs_estrito)
        except pd.errors.ParserError as exc:
            texto = str(exc)
            descartadas = texto.count("Skipping line")
            if not descartadas:
                descartadas = -1  # houve erro mas não foi possível quantificar
        except (ValueError, UnicodeDecodeError):
            pass
        return df, max(descartadas, 0)

    @classmethod
    def export_to_csv_bytes(cls, df: pd.DataFrame, sep: str = ";", encoding: str = "utf-8-sig") -> bytes:
        """Exporta o DataFrame para bytes CSV com suporte ao Excel (utf-8-sig e ponto e vírgula)."""
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, sep=sep, index=False, encoding=encoding)
        return csv_buffer.getvalue().encode(encoding)

    @classmethod
    def export_to_excel_bytes(
        cls,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        sheet_name: str = "Dados_Processados",
    ) -> bytes:
        """
        Exporta um DataFrame ou dicionário de DataFrames para bytes XLSX com formatação e ajuste automático de largura.
        """
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            if isinstance(data, dict):
                for s_name, s_df in data.items():
                    clean_sheet_name = str(s_name)[:31]  # Limite do Excel de 31 caracteres por aba
                    s_df.to_excel(writer, sheet_name=clean_sheet_name, index=False)
                    
                    worksheet = writer.sheets[clean_sheet_name]
                    for col in worksheet.columns:
                        max_len = 0
                        col_letter = col[0].column_letter
                        for cell in col:
                            try:
                                if cell.value:
                                    max_len = max(max_len, len(str(cell.value)))
                            except Exception:
                                pass
                        worksheet.column_dimensions[col_letter].width = max(max_len + 3, 10)
            else:
                data.to_excel(writer, sheet_name=sheet_name, index=False)
                worksheet = writer.sheets[sheet_name]
                for col in worksheet.columns:
                    max_len = 0
                    col_letter = col[0].column_letter
                    for cell in col:
                        try:
                            if cell.value:
                                max_len = max(max_len, len(str(cell.value)))
                        except Exception:
                            pass
                    worksheet.column_dimensions[col_letter].width = max(max_len + 3, 10)

        excel_buffer.seek(0)
        return excel_buffer.getvalue()

    @staticmethod
    def get_sample_ecommerce_data() -> pd.DataFrame:
        """Cria um DataFrame de exemplo de vendas para teste instantâneo da aplicação."""
        data = {
            "ID_Pedido": [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010],
            "Data": [
                "2026-01-10", "2026-01-12", "2026-01-15", "2026-01-20", "2026-02-01",
                "2026-02-05", "2026-02-14", "2026-02-18", "2026-03-02", "2026-03-10"
            ],
            "Vendedor": [
                "Ana Silva", "Carlos Souza", "Beatriz Lima", "Ana Silva", "Carlos Souza",
                "Beatriz Lima", "Ana Silva", "Carlos Souza", "Beatriz Lima", "Ana Silva"
            ],
            "Regiao": ["Sudeste", "Sul", "Nordeste", "Sudeste", "Sul", "Nordeste", "Sudeste", "Sul", "Norte", "Sudeste"],
            "Categoria": ["Eletrônicos", "Móveis", "Eletrônicos", "Vestuário", "Móveis", "Vestuário", "Eletrônicos", "Móveis", "Eletrônicos", "Vestuário"],
            "Produto": [
                "Notebook Pro", "Mesa Ergonômica", "Smartphone 5G", "Camiseta Algodão", "Cadeira Gamer",
                "Calça Jeans", "Monitor 4K", "Estante Livros", "Tablet 10 pol", "Tênis Esportivo"
            ],
            "Quantidade": [2, 1, 3, 10, 2, 5, 2, 1, 4, 3],
            "Preco_Unitario": [4500.00, 850.00, 2800.00, 79.90, 1200.00, 159.90, 2100.00, 450.00, 1950.00, 299.90],
            "Status": [
                "Concluído", "Concluído", "Pendente", "Concluído", "Cancelado",
                "Concluído", "Concluído", "Concluído", "Pendente", "Concluído"
            ],
            "Desconto_Pct": [0.05, 0.00, 0.10, 0.15, 0.00, 0.05, 0.10, 0.00, 0.05, 0.10]
        }
        return pd.DataFrame(data)

    @staticmethod
    def get_sample_ecommerce_workbook() -> Dict[str, pd.DataFrame]:
        """Cria um conjunto multi-abas de exemplo com Vendas, Clientes e Produtos para testar relacionamentos."""
        vendas = pd.DataFrame({
            "ID_Pedido": [101, 102, 103, 104, 105, 106, 107, 108],
            "ID_Cliente": [1, 2, 1, 3, 4, 2, 5, 3],
            "ID_Produto": [501, 502, 503, 501, 504, 502, 505, 503],
            "Data": ["2026-01-15", "2026-01-18", "2026-01-22", "2026-02-05", "2026-02-12", "2026-02-20", "2026-03-01", "2026-03-10"],
            "Quantidade": [2, 1, 4, 1, 3, 2, 5, 1],
            "Status": ["Concluído", "Concluído", "Concluído", "Pendente", "Concluído", "Concluído", "Concluído", "Cancelado"]
        })

        clientes = pd.DataFrame({
            "ID_Cliente": [1, 2, 3, 4, 5],
            "Nome": ["Tech Solutions", "Mercado Global", "SuperVarejo", "Logix Brasil", "Nexus Indústria"],
            "Cidade": ["São Paulo", "Curitiba", "Rio de Janeiro", "Belo Horizonte", "Porto Alegre"],
            "Estado": ["SP", "PR", "RJ", "MG", "RS"],
            "Segmento": ["Corporativo", "Varejo", "Varejo", "Corporativo", "Indústria"]
        })

        produtos = pd.DataFrame({
            "ID_Produto": [501, 502, 503, 504, 505],
            "Nome_Produto": ["Notebook Pro", "Monitor 4K", "Teclado Mecânico", "Cadeira Ergonômica", "Mouse Sem Fio"],
            "Categoria": ["Informática", "Vídeo", "Periféricos", "Móveis", "Periféricos"],
            "Preco_Unitario": [5200.00, 2400.00, 350.00, 1450.00, 180.00]
        })

        metas = pd.DataFrame({
            "Estado": ["SP", "PR", "RJ", "MG", "RS"],
            "Meta_Mensal": [15000.00, 8000.00, 10000.00, 7000.00, 6000.00]
        })

        return {
            "Vendas": vendas,
            "Clientes": clientes,
            "Produtos": produtos,
            "Metas": metas,
        }
