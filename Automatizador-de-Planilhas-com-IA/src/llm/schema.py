"""Extrator de esquema e metadados de DataFrames e Workbooks para prompt de IA.

Ponto crítico de segurança: esta é a fronteira onde conteúdo NÃO CONFIÁVEL da planilha vira texto
de prompt. Duas responsabilidades:

1. **Neutralizar injection**: nomes de aba/coluna e valores de célula são sanitizados antes de
   serializar, para que não consigam (a) quebrar a estrutura do prompt, (b) fechar o bloco
   delimitado `<<<INICIO_DADOS_PLANILHA ... FIM_DADOS_PLANILHA>>>` ou (c) parecer um bloco de
   código/instrução.
2. **Respeitar orçamento de contexto**: o texto final é truncado em `max_prompt_chars`, para não
   estourar a janela do modelo nem o custo por chamada.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

import pandas as pd

#: Marcadores que o conteúdo da planilha não pode forjar.
_DELIMITADORES = ("<<<INICIO_DADOS_PLANILHA", "FIM_DADOS_PLANILHA>>>", "### ", "```")
#: Trechos que denunciam tentativa de manipular o modelo ou o sandbox.
_PADROES_SUSPEITOS = re.compile(
    r"ignore\s+(as\s+)?(instru|regras|orienta)"
    r"|desconsidere\s+(as\s+)?(instru|regras)"
    r"|system\s*:|assistant\s*:"
    r"|\bimport\s+(os|sys|subprocess|socket|shutil|ctypes)\b"
    r"|\b(os\.environ|popen|subprocess|__import__|eval\s*\(|exec\s*\(|open\s*\()",
    re.IGNORECASE,
)

#: Marca aplicada a conteúdo que disparou um padrão suspeito.
_MARCA_SUSPEITA = "[CONTEUDO_NAO_CONFIAVEL_REMOVIDO]"

#: Limite por valor de célula serializado.
_MAX_VALOR = 120
#: Limite por nome de coluna/aba.
_MAX_NOME = 120


def sanitize_texto(valor: Any, limite: int = _MAX_VALOR) -> str:
    """Sanitiza texto vindo da planilha para interpolação segura em prompt.

    - remove quebras de linha e tabulações (impedem forjar novas seções do prompt);
    - neutraliza os delimitadores do bloco de dados;
    - substitui conteúdo que parece instrução por uma marca explícita;
    - trunca em `limite` caracteres.
    """
    texto = str(valor)
    texto = texto.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    for delimitador in _DELIMITADORES:
        texto = texto.replace(delimitador, "[delimitador-removido]")
    if _PADROES_SUSPEITOS.search(texto):
        texto = _MARCA_SUSPEITA + " " + _PADROES_SUSPEITOS.sub("[...]", texto)
    texto = texto.strip()
    if len(texto) > limite:
        texto = texto[:limite] + "…"
    return texto


class DataFrameSchemaExtractor:
    """Extrai informações estruturais e estatísticas de DataFrames e Workbooks multi-abas."""

    @classmethod
    def extract_summary(cls, df: pd.DataFrame, max_sample_rows: int = 5) -> Dict[str, Any]:
        """Gera um resumo detalhado e compacto de um DataFrame para contextualizar o LLM."""
        total_rows, total_cols = df.shape
        columns_info: List[Dict[str, Any]] = []

        for col in df.columns:
            series = df[col]
            dtype = str(series.dtype)
            null_count = int(series.isna().sum())
            null_pct = round((null_count / total_rows * 100), 1) if total_rows > 0 else 0.0

            col_data: Dict[str, Any] = {
                "name": sanitize_texto(col, _MAX_NOME),
                "dtype": dtype,
                "null_count": null_count,
                "null_pct": null_pct,
            }

            unique_count = int(series.nunique(dropna=True))
            col_data["unique_count"] = unique_count
            if unique_count <= 8:
                col_data["unique_sample"] = [
                    sanitize_texto(x) for x in series.dropna().unique()[:8]
                ]

            if pd.api.types.is_numeric_dtype(series) and series.dropna().shape[0] > 0:
                col_data["min"] = float(series.min()) if not pd.isna(series.min()) else None
                col_data["max"] = float(series.max()) if not pd.isna(series.max()) else None
                col_data["mean"] = round(float(series.mean()), 2) if not pd.isna(series.mean()) else None

            columns_info.append(col_data)

        sample_df = df.head(max_sample_rows)
        sample_records = [
            {sanitize_texto(chave, _MAX_NOME): sanitize_texto(valor) for chave, valor in linha.items()}
            for linha in sample_df.to_dict(orient="records")
        ]

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
            sheets_summary[sanitize_texto(sheet_name, _MAX_NOME)] = cls.extract_summary(
                sheet_df, max_sample_rows=max_sample_rows
            )
        return {
            "total_sheets": len(dfs),
            "sheet_names": [sanitize_texto(nome, _MAX_NOME) for nome in dfs.keys()],
            "sheets": sheets_summary,
        }

    @classmethod
    def format_single_df_schema(
        cls, df: pd.DataFrame, sheet_title: str = "df", max_sample_rows: int = 5
    ) -> str:
        """Formata o esquema de um único DataFrame."""
        summary = cls.extract_summary(df, max_sample_rows=max_sample_rows)
        titulo = sanitize_texto(sheet_title, _MAX_NOME)

        output_lines = [
            f"#### ABA / TABELA: `{titulo}` ({summary['total_rows']} linhas x {summary['total_columns']} colunas)",
            "- Colunas e Tipos:",
        ]

        for col in summary["columns"]:
            line = f"  * `{col['name']}` ({col['dtype']}) | Nulos: {col['null_count']} ({col['null_pct']}%)"
            if col.get("unique_sample"):
                line += f" | Exemplos: {col['unique_sample']}"
            elif col.get("min") is not None:
                line += f" | Min: {col['min']}, Max: {col['max']}, Média: {col['mean']}"
            output_lines.append(line)

        output_lines.append("\n- Amostra das primeiras linhas:")
        sample_rows = summary["sample_rows"]
        if sample_rows:
            headers = list(sample_rows[0].keys())
            output_lines.append("| " + " | ".join(headers) + " |")
            output_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for linha in sample_rows:
                output_lines.append(
                    "| " + " | ".join(str(linha.get(h, "")) for h in headers) + " |"
                )
        else:
            output_lines.append("*(Aba vazia)*")

        return "\n".join(output_lines)

    @classmethod
    def format_schema_for_prompt(
        cls,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        max_sample_rows: int = 5,
        max_prompt_chars: Optional[int] = None,
    ) -> str:
        """Formata o esquema completo (tabela única ou workbook) para o prompt da IA."""
        if isinstance(data, pd.DataFrame):
            return cls._truncar(
                cls.format_single_df_schema(data, sheet_title="df", max_sample_rows=max_sample_rows),
                max_prompt_chars,
            )

        if len(data) == 1:
            sheet_name = list(data.keys())[0]
            return cls._truncar(
                cls.format_single_df_schema(
                    data[sheet_name], sheet_title=sheet_name, max_sample_rows=max_sample_rows
                ),
                max_prompt_chars,
            )

        lines = [
            f"### ESTRUTURA DO WORKBOOK (Total de {len(data)} abas):",
            "Abas disponíveis no dicionário `dfs`: "
            + sanitize_texto(list(data.keys()), 400) + "\n",
        ]

        for sheet_name, sheet_df in data.items():
            lines.append(
                cls.format_single_df_schema(
                    sheet_df, sheet_title=sheet_name, max_sample_rows=max_sample_rows
                )
            )
            lines.append("\n" + "-" * 40 + "\n")

        return cls._truncar("\n".join(lines), max_prompt_chars)

    @staticmethod
    def _truncar(texto: str, limite: Optional[int]) -> str:
        """Aplica o orçamento de contexto, informando no fim que houve corte."""
        if not limite or len(texto) <= limite:
            return texto
        aviso = "\n\n[esquema truncado: o workbook é maior do que o contexto permitido]"
        return texto[: max(0, limite - len(aviso))] + aviso
