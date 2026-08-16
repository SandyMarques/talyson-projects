# 📊 Automatizador de Planilhas com IA (DeepSeek + Streamlit)

Aplicação web completa e robusta em Python para automação e manipulação inteligente de planilhas (`.xlsx` e `.csv`) a partir de comandos em linguagem natural (Português), utilizando a **API DeepSeek**, **Pandas** e **Streamlit**.

---

## 🚀 Funcionalidades

- 📁 **Suporte Multi-Abas Inteligente (Workbook Completo)**:
  - Leitura simultânea de todas as abas de arquivos Excel (`.xlsx`, `.xls`).
  - IA com visão contextual de todas as tabelas e capacidade de relacionar/cruzar abas (merges, PROCV, consolidações) automaticamente via prompt em linguagem natural.
  - Leitura inteligente de arquivos `.csv` com detecção automática de delimitador (`,`, `;`, `\t`) e encoding (`utf-8`, `latin-1`, `cp1252`).
  - Exportação em `.xlsx` formatado (preservando abas) e `.csv` (`utf-8-sig`).
- 🤖 **Motor de IA DeepSeek**:
  - Geração de código Pandas defensivo e eficiente a partir de instruções em português.
  - Suporte aos modelos `deepseek-chat` (DeepSeek-V3) e `deepseek-reasoner` (DeepSeek-R1).
  - Explicação amigável em português de todas as operações realizadas na planilha.
- 🛡️ **Sandbox de Execução Segura**:
  - Isolamento de execução com escopo restrito (`pd`, `np`, `datetime`, `re`, `math`).
  - Bloqueio estático e dinâmico de operações não seguras (`os`, `sys`, `subprocess`, `eval`, `open`).
  - Imutabilidade da base original (todas as operações são realizadas em cópias profundas).
- ⚡ **Auto-Healing de Erros**:
  - Se o código gerado falhar em tempo de execução (ex: tipo de dado incompatível ou acentuação em colunas), a IA analisa o traceback e autocorrige o script automaticamente (até 2 tentativas).
- ⏪ **Histórico e Pipeline de Ações**:
  - Empilhamento de transformações sucessivas.
  - Botão **Desfazer (Undo)** para voltar à etapa anterior.
  - Botão **Resetar** para restaurar a planilha original.
- 📊 **Visualização e Gráficos**:
  - Resumo de métricas (linhas, colunas, células vazias, memória).
  - Resumo de impacto (variação de linhas, colunas adicionadas/removidas, tempo de execução).
  - Gráficos automáticos (Barras, Linhas, Área) para dados agregados.
  - Base de demonstração integrada para testes rápidos com 1 clique.

---

## 🏗️ Arquitetura do Projeto

```
Automatizador de Planilhas com IA/
├── app.py                        # Ponto de entrada da aplicação Streamlit
├── requirements.txt              # Dependências do projeto
├── .env.example                  # Template de variáveis de ambiente
├── README.md                     # Documentação do projeto
├── src/
│   ├── core/
│   │   ├── config.py             # Configurações gerais e parâmetros da DeepSeek
│   │   └── file_handler.py       # Leitura, parsing e exportação de CSV e XLSX
│   ├── llm/
│   │   ├── client.py             # Cliente DeepSeek (OpenAI-compatible)
│   │   ├── prompts.py            # Prompts de engenharia de contexto e auto-healing
│   │   └── schema.py             # Extrator de esquema e metadados de DataFrames
│   ├── engine/
│   │   ├── code_executor.py      # Sandbox de execução segura
│   │   └── error_recovery.py     # Pipeline de execução com autocorreção
│   └── ui/
│       ├── components.py         # Componentes visuais do Streamlit
│       └── styles.py             # CSS customizado e design system
└── tests/
    ├── test_file_handler.py      # Testes de arquivos e encodings
    ├── test_schema.py            # Testes do extrator de esquema
    ├── test_code_executor.py     # Testes de execução segura e bloqueio
    └── test_error_recovery.py    # Testes do ciclo de auto-healing
```

---

## ⚙️ Instalação e Configuração

### 1. Clonar ou Acessar a Pasta do Projeto
```bash
cd "C:\Users\User\Documents\Projetos\Automatizador-de-Planilhas-com-IA"
```

### 2. Criar e Ativar Ambiente Virtual (Recomendado)
```bash
python -m venv venv
# No Windows:
.\venv\Scripts\activate
```

### 3. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 4. Configurar a Chave de API
Copie o arquivo `.env.example` para `.env` e adicione sua chave de API da DeepSeek:
```env
DEEPSEEK_API_KEY=sua_chave_deepseek_aqui
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```
*(Nota: Você também pode inserir a chave diretamente na barra lateral da aplicação web ao executá-la).*

---

## ▶️ Como Executar a Aplicação

Execute o comando no terminal:
```bash
streamlit run app.py
```
A aplicação será aberta automaticamente no seu navegador padrão (geralmente em `http://localhost:8501`).

---

## 🧪 Como Rodar os Testes Automatizados

Para rodar toda a suíte de testes com `pytest`:
```bash
python -m pytest -v
```

---

## 💡 Exemplos de Comandos em Português

- *"Crie uma coluna chamada 'Valor_Total' multiplicando a Quantidade pelo Preco_Unitario."*
- *"Filtre apenas os registros com Status igual a 'Concluído' e Região 'Sudeste'."*
- *"Agrupe por Categoria, calcule a soma da Quantidade e a média do Preço, e ordene pelo total decrescente."*
- *"Crie uma coluna de comissão de 5% sobre as vendas acima de R$ 1.000."*
- *"Remova todas as linhas com valores nulos e converta as datas para o padrão dd/mm/aaaa."*
