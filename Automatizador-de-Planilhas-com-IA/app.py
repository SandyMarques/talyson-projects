"""Aplicação Principal Streamlit: Automatizador de Planilhas com IA e Suporte Multi-Abas."""

import io
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st

from src.core.config import config
from src.core.file_handler import FileHandler
from src.engine.error_recovery import TransformationPipeline
from src.llm.client import DeepSeekClient
from src.ui.components import (
    render_ai_explanation,
    render_chart_suggestions,
    render_code_expander,
    render_dataframe_metrics,
    render_diff_summary,
    render_download_buttons,
    render_header,
    render_workbook_overview,
)
from src.ui.styles import CUSTOM_CSS

# Configuração da página Streamlit
st.set_page_config(
    page_title="Automatizador de Planilhas com IA",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Injeção de CSS Customizado
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# Inicialização do Session State
def init_session_state():
    if "dfs_original" not in st.session_state:
        st.session_state.dfs_original = None  # Dict[str, pd.DataFrame]
    if "dfs_current" not in st.session_state:
        st.session_state.dfs_current = None  # Dict[str, pd.DataFrame]
    if "df_current" not in st.session_state:
        st.session_state.df_current = None  # DataFrame principal/ativo
    if "history" not in st.session_state:
        st.session_state.history = []  # Histórico de transformações
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "file_name" not in st.session_state:
        st.session_state.file_name = "planilha.xlsx"
    if "instrucao_input" not in st.session_state:
        st.session_state.instrucao_input = ""
    if "abas_preservadas" not in st.session_state:
        st.session_state.abas_preservadas = []


init_session_state()


# Barra Lateral: Configurações, Bases de Exemplo e Histórico
def render_sidebar():
    with st.sidebar:
        st.markdown("### ⚙️ Configurações da IA")

        api_key = st.text_input(
            "DeepSeek API Key",
            value=config.api_key or "",
            type="password",
            help="Insira sua chave de API DeepSeek ou defina DEEPSEEK_API_KEY no arquivo .env",
        )

        with st.expander("🔧 Parâmetros Avançados", expanded=False):
            base_url = st.text_input(
                "Base URL",
                value=config.base_url,
                help="Endpoint compatível com OpenAI (ex: https://api.deepseek.com ou Ollama local)",
            )
            model = st.selectbox(
                "Modelo",
                options=config.available_models,
                index=0,
                help="deepseek-chat (padrão) ou deepseek-reasoner",
            )
            temperature = st.slider(
                "Temperatura (Criatividade)",
                min_value=0.0,
                max_value=1.0,
                value=config.temperature,
                step=0.05,
            )

        st.markdown("---")
        st.markdown("### 🧪 Bases de Demonstração")
        if st.button("📚 Carregar Exemplo Multi-Abas (Vendas + Clientes + Produtos + Metas)", use_container_width=True):
            sample_workbook = FileHandler.get_sample_ecommerce_workbook()
            st.session_state.dfs_original = {k: v.copy(deep=True) for k, v in sample_workbook.items()}
            st.session_state.dfs_current = {k: v.copy(deep=True) for k, v in sample_workbook.items()}
            st.session_state.df_current = sample_workbook["Vendas"].copy(deep=True)
            st.session_state.file_name = "vendas_multi_abas_exemplo.xlsx"
            st.session_state.history = []
            st.session_state.last_result = None
            st.session_state.instrucao_input = ""
            st.success("Planilha multi-abas carregada com sucesso!")
            st.rerun()

        if st.button("📊 Carregar Tabela Única (Vendas Simples)", use_container_width=True):
            sample_df = FileHandler.get_sample_ecommerce_data()
            st.session_state.dfs_original = {"Vendas": sample_df.copy(deep=True)}
            st.session_state.dfs_current = {"Vendas": sample_df.copy(deep=True)}
            st.session_state.df_current = sample_df.copy(deep=True)
            st.session_state.file_name = "vendas_ecommerce_exemplo.xlsx"
            st.session_state.history = []
            st.session_state.last_result = None
            st.session_state.instrucao_input = ""
            st.success("Tabela de exemplo carregada!")
            st.rerun()

        st.markdown("---")
        st.markdown("### 🕒 Histórico de Operações")
        if st.session_state.history:
            st.caption(f"{len(st.session_state.history)} transformação(ões) aplicada(s)")
            for idx, item in enumerate(st.session_state.history, 1):
                st.markdown(f"**{idx}.** {item['instruction']}")

            col_undo, col_reset = st.columns(2)
            with col_undo:
                if st.button("↩️ Desfazer", use_container_width=True):
                    if len(st.session_state.history) > 1:
                        st.session_state.history.pop()
                        previous_state = st.session_state.history[-1]
                        st.session_state.dfs_current = {k: v.copy(deep=True) for k, v in previous_state["dfs"].items()}
                        st.session_state.df_current = previous_state["df"].copy(deep=True)
                        st.session_state.last_result = previous_state.get("result")
                    else:
                        st.session_state.history = []
                        st.session_state.dfs_current = {k: v.copy(deep=True) for k, v in st.session_state.dfs_original.items()}
                        st.session_state.df_current = list(st.session_state.dfs_current.values())[0].copy(deep=True)
                        st.session_state.last_result = None
                    st.rerun()

            with col_reset:
                if st.button("🔄 Resetar", use_container_width=True):
                    st.session_state.history = []
                    st.session_state.dfs_current = {k: v.copy(deep=True) for k, v in st.session_state.dfs_original.items()}
                    st.session_state.df_current = list(st.session_state.dfs_current.values())[0].copy(deep=True)
                    st.session_state.last_result = None
                    st.rerun()
        else:
            st.info("Nenhuma modificação aplicada ainda.")

    return api_key, base_url, model, temperature


#: Máximo de versões guardadas no histórico. Cada entrada guarda uma cópia do workbook, então
#: sem teto a memória de uma sessão cresce sem limite conforme o usuário itera.
MAX_HISTORICO = 10


def _registrar_historico(instruction: str) -> None:
    """Guarda um ponto de restauração (undo) descartando os mais antigos."""
    st.session_state.history.append({
        "instruction": instruction,
        "dfs": {k: v.copy(deep=True) for k, v in st.session_state.dfs_current.items()},
        "df": st.session_state.df_current.copy(deep=True),
        "result": st.session_state.last_result,
    })
    if len(st.session_state.history) > MAX_HISTORICO:
        st.session_state.history = st.session_state.history[-MAX_HISTORICO:]


def _mesclar_resultado(
    abas_anteriores: Dict[str, pd.DataFrame],
    resultado,
) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """Combina o resultado do pipeline com as abas que ele não mencionou.

    Regra: a transformação só substitui as abas que ela declarou em `dfs_result`. As demais são
    preservadas intactas. Sem isso, pedir uma mudança em uma aba apagava as outras da tela e do
    arquivo exportado, em silêncio.

    Retorna `(abas_para_estado, nomes_preservados)` — função pura, testável sem Streamlit.
    """
    if not getattr(resultado, "success", False):
        return dict(abas_anteriores), []

    if resultado.final_dfs:
        abas = dict(resultado.final_dfs)
        preservadas = [
            nome for nome in abas_anteriores
            if nome not in abas and nome != "Resultado"
        ]
        for nome in preservadas:
            abas[nome] = abas_anteriores[nome]
        return abas, preservadas

    if resultado.final_df is not None:
        return {"Resultado": resultado.final_df}, []

    return dict(abas_anteriores), []


# Execução Principal da Interface
def main():
    render_header()
    api_key, base_url, model, temperature = render_sidebar()

    # Área de Upload de Arquivo
    st.markdown("### 1. Seleção de Arquivo")
    uploaded_file = st.file_uploader(
        "Arraste e solte ou selecione sua planilha (.xlsx, .xls, .csv):",
        type=["xlsx", "xls", "csv"],
        help="Formatos aceitos: Excel com todas as abas (.xlsx, .xls) e CSV (.csv)",
    )

    if uploaded_file is not None:
        try:
            # Se for um novo arquivo, carregar todas as abas
            if st.session_state.file_name != uploaded_file.name:
                raw_bytes = uploaded_file.read()
                dfs_loaded, meta = FileHandler.load_all_sheets(raw_bytes, uploaded_file.name)

                st.session_state.dfs_original = {k: v.copy(deep=True) for k, v in dfs_loaded.items()}
                st.session_state.dfs_current = {k: v.copy(deep=True) for k, v in dfs_loaded.items()}
                st.session_state.df_current = list(dfs_loaded.values())[0].copy(deep=True)
                st.session_state.file_name = uploaded_file.name
                st.session_state.history = []
                st.session_state.last_result = None
                st.session_state.instrucao_input = ""
                st.success(f"Arquivo `{uploaded_file.name}` carregado com sucesso! ({len(dfs_loaded)} aba(s) detectada(s))")

        except Exception as file_err:
            st.error(f"Erro ao carregar o arquivo: {str(file_err)}")

    # Se há dados carregados
    if st.session_state.dfs_current is not None:
        dfs = st.session_state.dfs_current

        st.markdown("---")
        st.markdown("### 2. Visão Geral das Abas Carregadas")
        
        if len(dfs) > 1:
            render_workbook_overview(dfs)
            
            # Abas visuais do Streamlit para cada planilha
            sheet_names = list(dfs.keys())
            tabs = st.tabs([f"📄 Aba: {name}" for name in sheet_names])
            for i, sheet_name in enumerate(sheet_names):
                with tabs[i]:
                    sheet_df = dfs[sheet_name]
                    render_dataframe_metrics(sheet_df)
                    st.dataframe(sheet_df, use_container_width=True, height=220)
        else:
            single_sheet_name = list(dfs.keys())[0]
            single_df = dfs[single_sheet_name]
            render_dataframe_metrics(single_df)
            st.dataframe(single_df, use_container_width=True, height=260)

        st.markdown("---")
        st.markdown("### 3. O que você deseja fazer com a planilha?")

        # Sugestões Rápidas de Prompts Contextualizadas
        st.markdown("**💡 Sugestões rápidas de comandos:**")
        sug_col1, sug_col2, sug_col3, sug_col4 = st.columns(4)

        # As sugestões escrevem direto no widget (via `key`) e forçam rerun imediato. Antes o
        # valor ia para `prompt_suggestion` e era repassado como `value=`, então só aparecia no
        # rerun seguinte e nunca saía da caixa depois.
        def _usar_sugestao(texto: str) -> None:
            st.session_state.instrucao_input = texto
            st.rerun()

        sugestoes_multi = [
            (sug_col1, "🔗 Cruzar Vendas + Clientes",
             "Cruze a aba 'Vendas' com a aba 'Clientes' usando o ID_Cliente e adicione Nome, Estado e Segmento."),
            (sug_col2, "💰 Calcular Total e Lucro",
             "Cruze Vendas com Produtos pelo ID_Produto, calcule o Faturamento (Quantidade * Preco_Unitario) e ordene decrescente."),
            (sug_col3, "🎯 Comparar Real vs Metas",
             "Cruze Vendas com Clientes e Produtos para calcular o Faturamento Total por Estado, e compare com a aba Metas."),
            (sug_col4, "📊 Faturamento por Segmento",
             "Junte Vendas, Clientes e Produtos e gere um resumo com o Total de Vendas por Segmento e Estado."),
        ]
        sugestoes_simples = [
            (sug_col1, "➕ Criar Total = Qtd * Preço",
             "Crie uma nova coluna chamada 'Total' multiplicando a coluna de quantidade pela coluna de preço unitário."),
            (sug_col2, "🔍 Filtrar Concluídos",
             "Filtre a tabela mantendo apenas os registros onde o Status seja 'Concluído'."),
            (sug_col3, "📊 Agrupar por Categoria",
             "Agrupe os dados por Categoria ou Vendedor e calcule a soma da quantidade e faturamento total."),
            (sug_col4, "🧹 Limpar e Tratar Dados",
             "Remova linhas duplicadas e preencha valores numéricos vazios com zero."),
        ]
        for coluna, rotulo, texto in (sugestoes_multi if len(dfs) > 1 else sugestoes_simples):
            with coluna:
                if st.button(rotulo, use_container_width=True):
                    _usar_sugestao(texto)

        # Caixa de texto para instrução
        user_instruction = st.text_area(
            "Descreva sua instrução em português (a IA sabe quais abas usar):",
            key="instrucao_input",
            placeholder="Exemplo: Junte a aba Vendas com a aba Clientes pelo ID_Cliente, filtre apenas vendas de SP e crie o cálculo de Faturamento.",
            height=95,
        )

        execute_button = st.button("⚡ Executar Manipulação Inteligente com IA", type="primary", use_container_width=True)

        if execute_button:
            if not user_instruction or not user_instruction.strip():
                st.warning("Por favor, digite o que deseja fazer com a planilha.")
            elif not api_key:
                st.error("Por favor, insira sua DeepSeek API Key na barra lateral à esquerda.")
            else:
                client = DeepSeekClient(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    temperature=temperature,
                )
                pipeline = TransformationPipeline(client=client, max_retries=config.max_retries)

                status_placeholder = st.empty()
                with st.spinner("A IA está analisando todas as abas da planilha e gerando o código otimizado..."):
                    def update_status(msg):
                        status_placeholder.info(f"⏳ {msg}")

                    result = pipeline.run(
                        data=st.session_state.dfs_current,
                        user_instruction=user_instruction,
                        status_callback=update_status,
                    )

                status_placeholder.empty()

                if result.success:
                    abas_anteriores = dict(st.session_state.dfs_current)
                    resultado_abas, preservadas = _mesclar_resultado(abas_anteriores, result)
                    st.session_state.dfs_current = resultado_abas
                    st.session_state.abas_preservadas = preservadas

                    if result.final_df is not None:
                        st.session_state.df_current = result.final_df
                    elif resultado_abas:
                        st.session_state.df_current = next(iter(resultado_abas.values()))

                    st.session_state.last_result = result
                    _registrar_historico(user_instruction)
                    st.success("Manipulação realizada com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Falha ao realizar a manipulação: {result.error_message or 'erro não informado'}")
                    if result.attempts_history:
                        with st.expander("Ver detalhes do erro e tentativas de auto-healing"):
                            for att in result.attempts_history:
                                st.markdown(f"**Tentativa #{att.attempt_number}**")
                                st.code(att.code, language="python")
                                st.error(att.execution_result.traceback or att.execution_result.error)

        # Se houver resultado recente, exibir detalhes e opções de exportação
        if st.session_state.last_result and st.session_state.last_result.success:
            last_res = st.session_state.last_result
            last_attempt = last_res.attempts_history[-1] if last_res.attempts_history else None

            st.markdown("---")
            st.markdown("### 4. Resultado da Transformação")

            # Explicação da IA
            render_ai_explanation(
                last_res.final_explanation,
                healing_applied=last_res.healing_applied,
            )

            # Aviso de abas preservadas: transparência sobre o que a IA não tocou.
            if st.session_state.get("abas_preservadas"):
                st.info(
                    "Abas não mencionadas pela transformação foram preservadas intactas: "
                    + ", ".join(f"`{nome}`" for nome in st.session_state.abas_preservadas)
                )

            # Resumo do Impacto (Diff)
            if last_attempt:
                exec_data = last_attempt.execution_result
                render_diff_summary(
                    columns_added=exec_data.columns_added,
                    columns_removed=exec_data.columns_removed,
                    rows_delta=exec_data.rows_delta,
                    execution_time_ms=exec_data.execution_time_ms,
                )

            # Tabela Resultante Visual
            active_result_df = st.session_state.df_current
            if active_result_df is not None:
                st.markdown("##### 📋 Tabela Gerada:")
                st.dataframe(active_result_df, use_container_width=True, height=300)

            # Código Python Executado
            render_code_expander(
                last_res.final_code,
                total_attempts=last_res.total_attempts,
                attempts_history=last_res.attempts_history,
            )

            # Visualização Gráfica Sugerida
            if active_result_df is not None:
                render_chart_suggestions(active_result_df)

            # Central de Downloads
            st.markdown("---")
            st.markdown("### 5. Exportar Planilha")
            render_download_buttons(st.session_state.dfs_current, st.session_state.file_name)

    else:
        st.info("👆 Faça o upload de uma planilha ou clique em **'Carregar Exemplo Multi-Abas'** na barra lateral para começar!")


if __name__ == "__main__":
    main()
