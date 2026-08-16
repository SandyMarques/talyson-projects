"""Extrator de esquema e metadados de DataFrames e Workbooks para prompt de IA."""

import io
from typing import Any, Dict, List, Union
import pandas as pd


class DataFrameSchemaExtractor:
    """Extrai informações estruturais e estatísticas essenciais de DataFrames e Workbooks com múltiplas abas."""

    @classmethod
    def extract_summary(cls, df: pd.DataFrame, max_sample_rows: int = 5) -> Dict[str, Any]:
        """
        Gera um resumo detalhado e compacto de um DataFrame para contextualizar o LLM.
        """
        total_rows, total_cols = df.shape
        columns_info: List[Dict[str, Any]] = []

        for col in df.columns:
            series = df[col]
            dtype = str(series.dtype)
            null_count = int(series.isna().sum())
            null_pct = round((null_count / total_rows * 100), 1) if total_rows > 0 else 0.0

            col_data = {
                "name": str(col),
                "dtype": dtype,
                "null_count": null_count,
                "null_pct": null_pct,
            }

            # Amostra de valores únicos para variáveis categóricas ou com baixa cardinalidade
            unique_count = int(series.nunique(dropna=True))
            col_data["unique_count"] = unique_count
            if unique_count <= 8:
                col_data["unique_sample"] = [str(x) for x in series.dropna().unique()[:8]]

            # Estatísticas rápidas para variáveis numéricas
            if pd.api.types.is_numeric_dtype(series) and series.dropna().shape[0] > 0:
                col_data["min"] = float(series.min()) if not pd.isna(series.min()) else None
                col_data["max"] = float(series.max()) if not pd.isna(series.max()) else None
                col_data["mean"] = round(float(series.mean()), 2) if not pd.isna(series.mean()) else None

            columns_info.append(col_data)

        # Amostra das primeiras linhas
        sample_df = df.head(max_sample_rows)
        sample_records = sample_df.to_dict(orient="records")

        return {
            "total_rows": total_rows,
            "total_columns": total_cols,
            "columns": columns_info,
            "sample_rows": sample_records,
        }

    @classmethod
    def extract_multi_sheet_summary(
        cls, dfs: Dict[str, pd.DataFrame], max_sample_rows: int = 5
    ) -> Dict[str, Any]:
        """Gera resumo estrutural de todas as abas presentes no dicionário de DataFrames."""
        sheets_summary = {}
        for sheet_name, sheet_df in dfs.items():
            sheets_summary[sheet_name] = cls.extract_summary(sheet_df, max_sample_rows=max_sample_rows)
        return {
            "total_sheets": len(dfs),
            "sheet_names": list(dfs.keys()),
            "sheets": sheets_summary,
        }

    @classmethod
    def format_single_df_schema(cls, df: pd.DataFrame, sheet_title: str = "df", max_sample_rows: int = 5) -> str:
        """Formata o esquema de um único DataFrame."""
        summary = cls.extract_summary(df, max_sample_rows=max_sample_rows)
        
        output_lines = [
            f"#### ABA / TABELA: `{sheet_title}` ({summary['total_rows']} linhas x {summary['total_columns']} colunas)",
            f"- Colunas e Tipos:",
        ]

        for col in summary["columns"]:
            line = f"  * `{col['name']}` ({col['dtype']}) | Nulos: {col['null_count']} ({col['null_pct']}%)"
            if "unique_sample" in col and col["unique_sample"]:
                line += f" | Exemplos: {col['unique_sample']}"
            elif "min" in col and col["min"] is not None:
                line += f" | Min: {col['min']}, Max: {col['max']}, Média: {col['mean']}"
            output_lines.append(line)

        output_lines.append("\n- Amostra das primeiras linhas:")
        sample_df = df.head(max_sample_rows)
        if len(sample_df) > 0:
            headers = [str(c) for c in sample_df.columns]
            output_lines.append("| " + " | ".join(headers) + " |")
            output_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for _, row in sample_df.iterrows():
                row_vals = [str(row[c]) if not pd.isna(row[c]) else "null" for c in sample_df.columns]
                output_lines.append("| " + " | ".join(row_vals) + " |")
        else:
            output_lines.append("*(Aba vazia)*")

        return "\n".join(output_lines)

    @classmethod
    def format_schema_for_prompt(
        cls, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]], max_sample_rows: int = 5
    ) -> str:
        """
        Formata o esquema completo (seja uma única tabela ou um Workbook com múltiplas abas) para o prompt da IA.
        """
        if isinstance(data, pd.DataFrame):
            return cls.format_single_df_schema(data, sheet_title="df", max_sample_rows=max_sample_rows)

        # Se for um dicionário com múltiplas abas
        if len(data) == 1:
            sheet_name = list(data.keys())[0]
            return cls.format_single_df_schema(data[sheet_name], sheet_title=sheet_name, max_sample_rows=max_sample_rows)

        lines = [
            f"### ESTRUTURA DO WORKBOOK (Total de {len(data)} abas):",
            f"Abas disponíveis no dicionário `dfs`: {list(data.keys())}\n",
        ]

        for sheet_name, sheet_df in data.items():
            lines.append(cls.format_single_df_schema(sheet_df, sheet_title=sheet_name, max_sample_rows=max_sample_rows))
            lines.append("\n" + "-" * 40 + "\n")

        return "\n".join(lines)
