"""Manipulador de arquivos para leitura e exportação de CSV e XLSX."""

import io
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd


class FileHandler:
    """Responsável por carregar e exportar planilhas em múltiplos formatos com robustez e suporte multi-abas."""

    SUPPORTED_ENCODINGS = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]
    SUPPORTED_DELIMITERS = [",", ";", "\t", "|"]

    @classmethod
    def load_all_sheets(
        cls,
        file_input: Union[str, io.BytesIO, io.StringIO, bytes],
        filename: str,
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, any]]:
        """
        Carrega todas as abas de um arquivo Excel (.xlsx, .xls) ou um CSV como dicionário de DataFrames.
        Retorna (Dict[nome_aba, DataFrame], metadados).
        """
        lower_name = filename.lower()
        if lower_name.endswith((".xlsx", ".xls")):
            return cls.load_excel_all_sheets(file_input)
        elif lower_name.endswith(".csv"):
            df, meta = cls.load_csv(file_input)
            meta["sheets"] = ["Planilha"]
            return {"Planilha": df}, meta
        else:
            raise ValueError(f"Formato de arquivo não suportado: {filename}. Utilize .csv, .xlsx ou .xls")

    @classmethod
    def load_file(
        cls,
        file_input: Union[str, io.BytesIO, io.StringIO, bytes],
        filename: str,
        sheet_name: Optional[Union[str, int]] = 0,
    ) -> Tuple[pd.DataFrame, Dict[str, any]]:
        """
        Carrega um arquivo CSV ou aba específica de XLSX/XLS para DataFrame único.
        Retorna (DataFrame, metadados_de_leitura).
        """
        lower_name = filename.lower()
        if lower_name.endswith((".xlsx", ".xls")):
            return cls.load_excel(file_input, sheet_name=sheet_name)
        elif lower_name.endswith(".csv"):
            return cls.load_csv(file_input)
        else:
            raise ValueError(f"Formato de arquivo não suportado: {filename}. Utilize .csv, .xlsx ou .xls")

    @classmethod
    def get_excel_sheets(cls, file_input: Union[str, io.BytesIO, bytes]) -> List[str]:
        """Obtém a lista de abas (planilhas) disponíveis no arquivo Excel."""
        if isinstance(file_input, bytes):
            file_input = io.BytesIO(file_input)
        excel_file = pd.ExcelFile(file_input, engine="openpyxl")
        return excel_file.sheet_names

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

        # sheet_name=None lê todas as abas como dicionário
        dict_dfs = pd.read_excel(file_input, sheet_name=None, engine="openpyxl")
        sheets = list(dict_dfs.keys())

        total_rows = sum(len(df) for df in dict_dfs.values())
        metadata = {
            "format": "excel",
            "sheets": sheets,
            "total_sheets": len(sheets),
            "total_rows": total_rows,
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

        last_error = None
        for encoding in cls.SUPPORTED_ENCODINGS:
            try:
                decoded_sample = raw_bytes[:4096].decode(encoding)
            except UnicodeDecodeError:
                continue

            best_delimiter = ","
            best_count = -1
            for delim in cls.SUPPORTED_DELIMITERS:
                count = decoded_sample.count(delim)
                if count > best_count:
                    best_count = count
                    best_delimiter = delim

            try:
                stream = io.BytesIO(raw_bytes)
                df = pd.read_csv(stream, encoding=encoding, sep=best_delimiter, on_bad_lines="skip")
                
                if len(df.columns) == 1 and best_delimiter != ";":
                    for alt_delim in [d for d in cls.SUPPORTED_DELIMITERS if d != best_delimiter]:
                        stream.seek(0)
                        df_alt = pd.read_csv(stream, encoding=encoding, sep=alt_delim, on_bad_lines="skip")
                        if len(df_alt.columns) > 1:
                            df = df_alt
                            best_delimiter = alt_delim
                            break

                metadata = {
                    "format": "csv",
                    "encoding": encoding,
                    "delimiter": best_delimiter,
                    "rows": len(df),
                    "columns": len(df.columns),
                    "sheets": ["Planilha"],
                }
                return df, metadata
            except Exception as e:
                last_error = e
                continue

        try:
            stream = io.BytesIO(raw_bytes)
            df = pd.read_csv(stream, sep=None, engine="python", on_bad_lines="skip")
            return df, {
                "format": "csv",
                "encoding": "auto-fallback",
                "delimiter": "auto",
                "rows": len(df),
                "columns": len(df.columns),
                "sheets": ["Planilha"],
            }
        except Exception as fallback_error:
            raise ValueError(f"Não foi possível decodificar o arquivo CSV: {last_error or fallback_error}")

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
