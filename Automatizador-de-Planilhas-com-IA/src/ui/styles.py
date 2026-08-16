"""Estilos CSS customizados para a interface Streamlit."""

CUSTOM_CSS = """
<style>
/* Tipografia e layout global */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Header estilizado */
.app-header {
    background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
    padding: 1.5rem 2rem;
    border-radius: 12px;
    color: #FFFFFF;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}
.app-header h1 {
    font-size: 1.8rem;
    font-weight: 700;
    margin: 0;
    color: #FFFFFF;
}
.app-header p {
    font-size: 0.95rem;
    color: #94A3B8;
    margin: 0.4rem 0 0 0;
}

/* Cards de estatísticas e métricas */
.metric-card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    text-align: left;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.metric-card:hover {
    border-color: #CBD5E1;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
}
.metric-title {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748B;
    font-weight: 600;
    margin-bottom: 0.3rem;
}
.metric-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: #0F172A;
}

/* Card de explicação da IA */
.ai-explanation-box {
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-left: 5px solid #22C55E;
    border-radius: 8px;
    padding: 1.2rem 1.4rem;
    margin: 1rem 0;
    color: #166534;
}
.ai-explanation-box h4 {
    margin: 0 0 0.5rem 0;
    font-size: 1.05rem;
    font-weight: 600;
    color: #15803D;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.ai-explanation-box p, .ai-explanation-box li {
    font-size: 0.95rem;
    line-height: 1.5;
    color: #14532D;
}

/* Card de Auto-Healing */
.healing-badge {
    display: inline-flex;
    align-items: center;
    background: #FEF3C7;
    border: 1px solid #FDE68A;
    color: #B45309;
    padding: 0.25rem 0.6rem;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}

/* Barra de Destaque para Diffs */
.diff-badge-add {
    background: #DCFCE7;
    color: #15803D;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.82rem;
    font-weight: 600;
}
.diff-badge-del {
    background: #FEE2E2;
    color: #B91C1C;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.82rem;
    font-weight: 600;
}

/* Botões de sugestão */
.prompt-chip {
    display: inline-block;
    background: #F1F5F9;
    border: 1px solid #E2E8F0;
    color: #334155;
    padding: 0.35rem 0.75rem;
    border-radius: 20px;
    font-size: 0.85rem;
    cursor: pointer;
    margin: 0.2rem;
    transition: all 0.2s ease;
}
.prompt-chip:hover {
    background: #E2E8F0;
    border-color: #CBD5E1;
}
</style>
"""
