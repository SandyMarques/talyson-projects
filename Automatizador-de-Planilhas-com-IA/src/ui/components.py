"""Componentes visuais reutilizáveis para a aplicação Streamlit com suporte a múltiplas abas."""

from typing import Dict, List, Optional, Union
import pandas as pd
import streamlit as st

from src.core.file_handler import FileHandler


def render_header():
    """Renderiza o cabeçalho principal da aplicação."""
    st.markdown(
        """
        <div class="app-header">
            <h1>📊 Automatizador de Planilhas com IA</h1>
            <p>Carregue planilhas <b>.xlsx</b> (com todas as abas) ou <b>.csv</b> e descreva suas manipulações em linguagem natural. A IA DeepSeek entende o contexto completo, cruza abas e executa as transformações com segurança.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dataframe_metrics(df: pd.DataFrame, label: str = "Resumo da Base"):
    """Exibe métricas rápidas de um DataFrame."""
    total_rows, total_cols = df.shape
    total_nulls = int(df.isna().sum().sum())
    memory_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">Linhas</div>
                <div class="metric-value">{total_rows:,}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">Colunas</div>
                <div class="metric-value">{total_cols}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">Células Vazias</div>
                <div class="metric-value">{total_nulls:,}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-title">Memória</div>
                <div class="metric-value">{memory_mb:.2f} MB</div>
            </div>""",
            unsafe_allow_html=True,
        )


def render_workbook_overview(dfs: Dict[str, pd.DataFrame]):
    """Exibe resumo visual de todas as abas disponíveis no arquivo."""
    total_sheets = len(dfs)
    total_rows = sum(len(df) for df in dfs.values())
    
    st.markdown(
        f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 18px; margin-bottom: 16px;">
            <span style="font-weight: 600; color: #1e293b; font-size: 1.05rem;">📚 Arquivo Multi-Abas: </span>
            <span style="color: #3b82f6; font-weight: bold;">{total_sheets} aba(s) carregada(s)</span>
            <span style="color: #64748b; font-size: 0.9rem;"> ({total_rows:,} linhas totais no arquivo)</span>
            <div style="margin-top: 6px; display: flex; gap: 8px; flex-wrap: wrap;">
                {' '.join([f'<span style="background: #e0e7ff; color: #3730a3; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; font-weight: 500;">📄 {sheet} ({len(df)} linhas)</span>' for sheet, df in dfs.items()])}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_diff_summary(
    columns_added: List[str],
    columns_removed: List[str],
    rows_delta: int,
    execution_time_ms: float,
):
    """Exibe resumo do impacto da transformação."""
    st.markdown("##### 📌 Resumo do Impacto da Transformação")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if rows_delta > 0:
            delta_str = f"+{rows_delta:,} linhas"
        elif rows_delta < 0:
            delta_str = f"{rows_delta:,} linhas"
        else:
            delta_str = "Sem alteração no número de linhas"
        st.markdown(f"**Variação de Linhas:** `{delta_str}`")

    with col2:
        st.markdown(f"**Tempo de Execução:** `{execution_time_ms:.1f} ms`")

    with col3:
        added_text = ", ".join([f"`{c}`" for c in columns_added]) if columns_added else "Nenhuma"
        st.markdown(f"**Novas Colunas:** {added_text}")

    if columns_removed:
        st.markdown(f"**Colunas Removidas:** {', '.join([f'`{c}`' for c in columns_removed])}")


def render_ai_explanation(explanation: str, healing_applied: bool = False):
    """Exibe a explicação amigável fornecida pela IA."""
    healing_html = ""
    if healing_applied:
        healing_html = '<div class="healing-badge">⚡ Auto-Healing Aplicado: O código foi corrigido automaticamente pela IA após ajuste de execução.</div>'

    st.markdown(
        f"""
        <div class="ai-explanation-box">
            {healing_html}
            <h4>💡 O que a IA realizou:</h4>
            <div>{explanation.replace(chr(10), '<br>')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_code_expander(code: str, total_attempts: int = 1, attempts_history: list = None):
    """Exibe o código Python executado com realce de sintaxe."""
    with st.expander(f"🐍 Ver Código Python Executado ({'Tentativa única' if total_attempts == 1 else f'{total_attempts} tentativas'})"):
        st.code(code, language="python")
        
        if attempts_history and len(attempts_history) > 1:
            st.markdown("---")
            st.caption("Histórico de tentativas e correções:")
            for att in attempts_history:
                with st.expander(f"Tentativa #{att.attempt_number} ({'Sucesso' if att.execution_result.success else 'Falha: ' + str(att.execution_result.error)})"):
                    st.code(att.code, language="python")
                    if not att.execution_result.success and att.execution_result.traceback:
                        st.error(att.execution_result.traceback)


def render_chart_suggestions(df: pd.DataFrame):
    """Oferece visualizações gráficas rápidas para o DataFrame transformado."""
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category", "string"]).columns.tolist()

    if numeric_cols and (categorical_cols or len(df) <= 50):
        with st.expander("📈 Visualização Gráfica Rápida", expanded=False):
            chart_col1, chart_col2, chart_col3 = st.columns(3)
            with chart_col1:
                chart_type = st.selectbox("Tipo de Gráfico", ["Barras", "Linhas", "Área"])
            with chart_col2:
                x_axis = st.selectbox("Eixo X (Categorias/Datas)", categorical_cols if categorical_cols else df.columns.tolist())
            with chart_col3:
                y_axis = st.selectbox("Eixo Y (Métrica)", numeric_cols)

            if x_axis and y_axis:
                chart_df = df[[x_axis, y_axis]].dropna().set_index(x_axis)
                if chart_type == "Barras":
                    st.bar_chart(chart_df)
                elif chart_type == "Linhas":
                    st.line_chart(chart_df)
                elif chart_type == "Área":
                    st.area_chart(chart_df)


def render_download_buttons(
    data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
    base_filename: str = "planilha_processada"
):
    """Renderiza botões estilizados de download em XLSX (com abas) e CSV."""
    clean_name = base_filename.rsplit(".", 1)[0]
    
    col1, col2 = st.columns(2)
    with col1:
        xlsx_data = FileHandler.export_to_excel_bytes(data)
        st.download_button(
            label="📥 Baixar Excel Completo (.xlsx)",
            data=xlsx_data,
            file_name=f"{clean_name}_transformada.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with col2:
        # Se for dict, pega a primeira aba ou a aba de resultado para o CSV
        if isinstance(data, dict):
            export_df = data.get("Resultado") or list(data.values())[0]
        else:
            export_df = data

        csv_data = FileHandler.export_to_csv_bytes(export_df, sep=";", encoding="utf-8-sig")
        st.download_button(
            label="📥 Baixar CSV da Tabela Ativa (.csv)",
            data=csv_data,
            file_name=f"{clean_name}_transformada.csv",
            mime="text/csv",
            use_container_width=True,
        )
