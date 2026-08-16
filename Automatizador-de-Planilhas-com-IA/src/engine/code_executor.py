"""Executor de código em sandbox segura para operações Pandas com suporte a múltiplas abas."""

import contextlib
import datetime
import io
import math
import re
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


@dataclass
class ExecutionResult:
    """Resultado da execução de um bloco de código de manipulação."""
    success: bool
    df_result: Optional[pd.DataFrame] = None
    dfs_result: Optional[Dict[str, pd.DataFrame]] = None
    executed_code: str = ""
    error: Optional[str] = None
    traceback: Optional[str] = None
    stdout: str = ""
    execution_time_ms: float = 0.0
    columns_added: List[str] = field(default_factory=list)
    columns_removed: List[str] = field(default_factory=list)
    rows_delta: int = 0


class SafeCodeExecutor:
    """Executa código Python/Pandas em um ambiente isolado com restrições de segurança."""

    # Palavras e padrões proibidos por segurança
    FORBIDDEN_PATTERNS = [
        r"\bimport\s+(os|sys|subprocess|shutil|socket|requests|urllib|http|webbrowser|pty|fcntl)\b",
        r"\bfrom\s+(os|sys|subprocess|shutil|socket|requests|urllib|http|webbrowser|pty|fcntl)\b",
        r"\b__import__\b",
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"\bopen\s*\(",
        r"\bgetattr\s*\(",
        r"\bsetattr\s*\(",
        r"\bdelattr\s*\(",
        r"\bglobals\s*\(",
        r"\blocals\s*\(",
        r"__subclasses__",
        r"__builtins__",
        r"__globals__",
    ]

    # Builtins permitidos com segurança
    SAFE_BUILTINS = {
        "abs": abs,
        "all": all,
        "any": any,
        "bin": bin,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "format": format,
        "frozenset": frozenset,
        "hex": hex,
        "int": int,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "iter": iter,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "oct": oct,
        "ord": ord,
        "pow": pow,
        "print": print,
        "range": range,
        "reversed": reversed,
        "round": round,
        "set": set,
        "slice": slice,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "type": type,
        "zip": zip,
        "True": True,
        "False": False,
        "None": None,
    }

    @classmethod
    def validate_code_safety(cls, code: str) -> Tuple[bool, Optional[str]]:
        """Verifica se o código contém chamadas ou importações perigosas."""
        for pattern in cls.FORBIDDEN_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"Código contém instrução não permitida por segurança: {pattern}"
        return True, None

    @classmethod
    def execute(
        cls,
        code: str,
        input_data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
    ) -> ExecutionResult:
        """
        Executa o código em uma cópia segura dos DataFrames de entrada (único ou dicionário de abas).
        """
        # Validação estática de segurança
        is_safe, security_msg = cls.validate_code_safety(code)
        if not is_safe:
            return ExecutionResult(
                success=False,
                executed_code=code,
                error=security_msg,
                traceback=security_msg,
            )

        # Preparar escopo de trabalho com cópias profundas
        if isinstance(input_data, dict):
            dfs_working = {k: v.copy(deep=True) for k, v in input_data.items()}
            first_df = list(dfs_working.values())[0] if dfs_working else pd.DataFrame()
            df_working = first_df.copy(deep=True)
            original_cols = set(df_working.columns)
            original_rows = len(df_working)
        else:
            df_working = input_data.copy(deep=True)
            dfs_working = {"Planilha": df_working}
            original_cols = set(df_working.columns)
            original_rows = len(df_working)

        # Ambiente seguro de execução
        safe_globals = {
            "__builtins__": cls.SAFE_BUILTINS,
            "pd": pd,
            "pandas": pd,
            "np": np,
            "numpy": np,
            "datetime": datetime,
            "re": re,
            "math": math,
        }

        local_scope = {
            "dfs": dfs_working,
            "df": df_working,
            "df_result": None,
            "dfs_result": None,
        }

        stdout_buffer = io.StringIO()
        start_time = time.perf_counter()

        try:
            with contextlib.redirect_stdout(stdout_buffer):
                exec(code, safe_globals, local_scope)
            
            elapsed_time_ms = (time.perf_counter() - start_time) * 1000

            # Obter os resultados gerados
            df_res = local_scope.get("df_result")
            dfs_res = local_scope.get("dfs_result")

            # Se gerou dicionário de abas
            if isinstance(dfs_res, dict):
                # Normalizar séries para dataframes dentro do dict se houver
                normalized_dfs = {}
                for k, v in dfs_res.items():
                    if isinstance(v, pd.Series):
                        normalized_dfs[k] = v.to_frame()
                    elif isinstance(v, pd.DataFrame):
                        normalized_dfs[k] = v
                
                if df_res is None and normalized_dfs:
                    df_res = list(normalized_dfs.values())[0]
                
                return ExecutionResult(
                    success=True,
                    df_result=df_res,
                    dfs_result=normalized_dfs,
                    executed_code=code,
                    stdout=stdout_buffer.getvalue(),
                    execution_time_ms=elapsed_time_ms,
                    columns_added=list(set(df_res.columns) - original_cols) if df_res is not None else [],
                    columns_removed=list(original_cols - set(df_res.columns)) if df_res is not None else [],
                    rows_delta=(len(df_res) - original_rows) if df_res is not None else 0,
                )

            # Se gerou um DataFrame único
            if df_res is None:
                # Se o código modificou 'df' in-place ou modificou o dict 'dfs'
                modified_df = local_scope.get("df")
                if isinstance(modified_df, pd.DataFrame):
                    df_res = modified_df

            if isinstance(df_res, pd.Series):
                df_res = df_res.to_frame()

            if not isinstance(df_res, pd.DataFrame):
                return ExecutionResult(
                    success=False,
                    executed_code=code,
                    error="O código executou, mas nem `df_result` nem `dfs_result` retornaram um pandas DataFrame válido.",
                    stdout=stdout_buffer.getvalue(),
                    execution_time_ms=elapsed_time_ms,
                )

            # Calcular deltas
            new_cols = set(df_res.columns)
            columns_added = list(new_cols - original_cols)
            columns_removed = list(original_cols - new_cols)
            rows_delta = len(df_res) - original_rows

            return ExecutionResult(
                success=True,
                df_result=df_res,
                dfs_result={"Resultado": df_res},
                executed_code=code,
                stdout=stdout_buffer.getvalue(),
                execution_time_ms=elapsed_time_ms,
                columns_added=columns_added,
                columns_removed=columns_removed,
                rows_delta=rows_delta,
            )

        except Exception as e:
            elapsed_time_ms = (time.perf_counter() - start_time) * 1000
            tb_lines = traceback.format_exc()
            return ExecutionResult(
                success=False,
                executed_code=code,
                error=str(e),
                traceback=tb_lines,
                stdout=stdout_buffer.getvalue(),
                execution_time_ms=elapsed_time_ms,
            )
