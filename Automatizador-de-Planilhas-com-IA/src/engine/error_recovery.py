"""Gerenciador de pipeline de execução e auto-healing com DeepSeek e suporte multi-abas."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Union
import pandas as pd

from src.engine.code_executor import ExecutionResult, SafeCodeExecutor
from src.llm.client import DeepSeekClient


@dataclass
class PipelineAttempt:
    """Registro de uma tentativa de execução no pipeline."""
    attempt_number: int
    code: str
    explanation: str
    execution_result: ExecutionResult
    was_repaired: bool = False


@dataclass
class PipelineResult:
    """Resultado final do processamento da instrução pelo pipeline."""
    success: bool
    final_df: Optional[pd.DataFrame] = None
    final_dfs: Optional[Dict[str, pd.DataFrame]] = None
    final_code: str = ""
    final_explanation: str = ""
    total_attempts: int = 1
    attempts_history: List[PipelineAttempt] = field(default_factory=list)
    error_message: Optional[str] = None
    healing_applied: bool = False


class TransformationPipeline:
    """Controla o fluxo completo: interpretação -> geração -> sandbox -> auto-healing."""

    def __init__(self, client: DeepSeekClient, max_retries: int = 2):
        self.client = client
        self.max_retries = max_retries

    def run(
        self,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        user_instruction: str,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> PipelineResult:
        """
        Executa a transformação no DataFrame ou Workbook com loop de auto-healing em caso de falha.
        """
        if status_callback:
            status_callback("Gerando código de manipulação com DeepSeek...")

        attempts: List[PipelineAttempt] = []

        # 1. Primeira tentativa: Geração inicial
        try:
            current_code, current_explanation = self.client.generate_transformation(
                data=data, user_instruction=user_instruction
            )
        except Exception as gen_err:
            return PipelineResult(
                success=False,
                error_message=f"Falha na comunicação com a IA: {str(gen_err)}",
            )

        if status_callback:
            status_callback("Executando código no ambiente seguro...")

        exec_res = SafeCodeExecutor.execute(current_code, data)
        attempts.append(
            PipelineAttempt(
                attempt_number=1,
                code=current_code,
                explanation=current_explanation,
                execution_result=exec_res,
                was_repaired=False,
            )
        )

        if exec_res.success:
            return PipelineResult(
                success=True,
                final_df=exec_res.df_result,
                final_dfs=exec_res.dfs_result,
                final_code=current_code,
                final_explanation=current_explanation,
                total_attempts=1,
                attempts_history=attempts,
                healing_applied=False,
            )

        # 2. Loop de Auto-Healing (tentativas de autocorreção)
        retry_count = 0
        while not exec_res.success and retry_count < self.max_retries:
            retry_count += 1
            if status_callback:
                status_callback(
                    f"Código falhou ({exec_res.error}). Acionando auto-healing DeepSeek (Tentativa {retry_count}/{self.max_retries})..."
                )

            try:
                repaired_code, repaired_explanation = self.client.repair_transformation(
                    data=data,
                    user_instruction=user_instruction,
                    failed_code=current_code,
                    error_message=exec_res.traceback or exec_res.error or "Erro de execução",
                )
            except Exception:
                break

            current_code = repaired_code
            current_explanation = repaired_explanation

            exec_res = SafeCodeExecutor.execute(current_code, data)
            attempts.append(
                PipelineAttempt(
                    attempt_number=retry_count + 1,
                    code=current_code,
                    explanation=current_explanation,
                    execution_result=exec_res,
                    was_repaired=True,
                )
            )

            if exec_res.success:
                return PipelineResult(
                    success=True,
                    final_df=exec_res.df_result,
                    final_dfs=exec_res.dfs_result,
                    final_code=current_code,
                    final_explanation=current_explanation,
                    total_attempts=retry_count + 1,
                    attempts_history=attempts,
                    healing_applied=True,
                )

        # Se todas as tentativas falharem
        last_attempt = attempts[-1] if attempts else None
        return PipelineResult(
            success=False,
            final_df=None,
            final_dfs=None,
            final_code=last_attempt.code if last_attempt else current_code,
            final_explanation=last_attempt.explanation if last_attempt else current_explanation,
            total_attempts=len(attempts),
            attempts_history=attempts,
            error_message=last_attempt.execution_result.error if last_attempt else "Erro desconhecido",
            healing_applied=(retry_count > 0),
        )
