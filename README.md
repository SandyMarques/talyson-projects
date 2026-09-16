# 🌟 Talyson Marques — Portfolio & Projects

Repositório central de portfólio profissional e projetos de Inteligência Artificial Generativa, Engenharia de Prompt, RAG (Retrieval-Augmented Generation), Automação de Dados e Infraestrutura de Redes.

🔗 **Live Portfolio (GitHub Pages):** [https://sandymarques.github.io/talyson-projects/](https://sandymarques.github.io/talyson-projects/)

---

## 📂 Estrutura do Repositório

| Caminho | Descrição |
| :--- | :--- |
| `site/` | Portfólio publicado no GitHub Pages (ver seção [Portfólio](#-portfólio-site)). |
| `Assistente-IA-com-RAG/` | Projeto 1 — chat RAG com FastAPI, LangChain e ChromaDB. |
| `Automatizador-de-Planilhas-com-IA/` | Projeto 2 — automação de planilhas com Streamlit e DeepSeek. |
| `motion-design/` | Skill de princípios de motion design usada como referência de animações. |
| `.github/workflows/static.yml` | Workflow de deploy do portfólio no GitHub Pages. |

> Os dois projetos possuem repositórios dedicados no GitHub e também são versionados nesta pasta.

---

## 🖥️ Portfólio (`site/`)

Portfólio profissional de posicionamento **híbrido — Administração e Tecnologia com o mesmo peso** —, em PT-BR e tom corporativo sóbrio. É um site estático de arquivo único por página, usando **Tailwind CSS e Lucide via CDN**, sem etapa de build, publicado pelo GitHub Pages.

### Páginas

| Arquivo | Descrição |
| :--- | :--- |
| `site/index.html` | Página principal: hero, perfil, trajetória, competências administrativas, projetos, atendimento virtual, habilidades e contato. |
| `site/blog.html` | Mini blog com artigos sobre automação, IA/RAG e organização de processos administrativos. |
| `site/projeto-detalhe.html` | Especificações, arquitetura e roadmap dos projetos em desenvolvimento (navegação por `?id=`). |
| `site/curriculo-talyson-marques.pdf` | Currículo para download (abre em nova aba). |

### Seções do `index.html`

- **Início** (`#inicio`) — apresentação e resumo de pontos fortes (Administração, Atendimento, Dados, Automação com IA).
- **Sobre** (`#sobre`) — perfil híbrido, formação em Redes de Computadores (SENAC-SP), idiomas (Português nativo • Inglês básico).
- **Trajetória** (`#experiencia`) — linha do tempo corporativa (Accenture Brasil / Projeto Vivere).
- **Competências administrativas** (`#competencias`) — descrição em linguagem de RH.
- **Projetos** (`#projetos`) — cards com status (disponível / em desenvolvimento) e links reais.
- **Atendimento virtual** (`#terminal`) — terminal corporativo com comandos (`sobre`, `projetos`, `blog`, `habilidades`, `contato`, `status`, `ajuda`, `limpar`).
- **Habilidades** (`#habilidades`) — rotinas administrativas, dados/ferramentas e automação com IA.
- **Contato** (`#contato`) — e-mail `talyson14marques@hotmail.com`, LinkedIn, GitHub e formulário via `mailto:`.

### Mini blog — artigos publicados

| Artigo | Categoria | Data |
| :--- | :--- | :--- |
| Do Caos da "Planilha Mestre" à Execução em 3 Segundos (Python e IA) | Automação com Python | 14/09/2026 |
| Além do "Ctrl + F": pasta corporativa em assistente inteligente com RAG | Inteligência Artificial & RAG | 08/09/2026 |
| A Casa em Ordem: 5 regras de governança administrativa antes do código | Administração & Processos | 01/09/2026 |

### Projetos em desenvolvimento

Detalhados em `site/projeto-detalhe.html`:

- Validador e auditor inteligente de documentos corporativos (`?id=validador-documental`)
- Painel de acompanhamento operacional e métricas (`?id=painel-operacional`)
- HelpDesk AI & Gestor de Métricas de SLA (`?id=helpdesk-sla`)
- Bot de Monitoramento de Infraestrutura e Redes (`?id=bot-infraestrutura`)
- Gestor de Prazos, Certidões e Contratos — Compliance Tracker (`?id=compliance-tracker`)

### Recursos técnicos

- **Tema claro/escuro** com persistência em `localStorage` (`tm-theme`) e sem flash na carga.
- **Acessibilidade**: skip-link, `:focus-visible`, `aria-label` e `prefers-reduced-motion`.
- **SEO/Compartilhamento**: `title`, meta `description`, `canonical` e Open Graph por página.
- **Deploy**: `.github/workflows/static.yml` publica a pasta `./site` no GitHub Pages a cada push em `main`.

---

## 🚀 Projetos Publicados

> Os 5 projetos em desenvolvimento estão listados na seção [Projetos em desenvolvimento](#projetos-em-desenvolvimento) e detalhados em `site/projeto-detalhe.html`.

### 🧠 1. [Assistente IA com RAG](https://github.com/SandyMarques/Assistente-IA-com-RAG)
> Chat inteligente corporativo com RAG (Retrieval-Augmented Generation) baseado em documentos locais (PDFs, TXT, Markdown, CSV, JSON), com eliminação de alucinações e citação de fontes em tempo real.

- **Stack:** Python 3.10+, FastAPI, LangChain, ChromaDB, Sentence-Transformers / OpenAI Embeddings, DeepSeek / OpenAI API, Docker & Docker Compose.
- **Destaques:**
  - Ingestão modular de arquivos com chunking inteligente (`RecursiveCharacterTextSplitter`).
  - Banco vetorial persistente com ChromaDB.
  - Endpoints REST assíncronos e Interface Web SPA integrada.
  - Suporte completo a Docker e suíte de testes automatizados com Pytest.
- 🔗 **Repositório dedicado:** [SandyMarques/Assistente-IA-com-RAG](https://github.com/SandyMarques/Assistente-IA-com-RAG)

---

### ⚙️ 2. [Automatizador de Planilhas com IA](https://github.com/SandyMarques/Automatizador-de-Planilhas-com-IA)
> Ferramenta interativa para manipulação, limpeza, cálculo e transformação de planilhas complexas (Excel/CSV) através de comandos em linguagem natural.

- **Stack:** Python 3.10+, Streamlit, Pandas, OpenPyXL, DeepSeek API (com fallback OpenAI), Pytest.
- **Destaques:**
  - Extração automática de metadados e schema de DataFrames multi-abas.
  - Geração de código Python seguro e auto-recuperação (Self-Healing Loop) em caso de erro de execução.
  - Histórico de versões de planilhas com funcionalidade de Desfazer/Refazer.
  - Exportação instantânea em formatos `.xlsx` e `.csv`.
- 🔗 **Repositório dedicado:** [SandyMarques/Automatizador-de-Planilhas-com-IA](https://github.com/SandyMarques/Automatizador-de-Planilhas-com-IA)

---

## 🛠️ Tecnologias & Competências

- **Linguagens:** Python, JavaScript, Shell Scripting, SQL, HTML5/CSS3.
- **IA & LLMs:** LangChain, ChromaDB, RAG Architecture, Prompt Engineering, DeepSeek, OpenAI API, HuggingFace.
- **Backend & APIs:** FastAPI, Uvicorn, RESTful APIs, Pydantic, Streamlit.
- **DevOps & Ferramentas:** Docker, Docker Compose, Git, GitHub Actions, Pytest.
- **Front-end & Publicação:** HTML5, CSS3, Tailwind CSS (CDN), Lucide Icons, GitHub Pages.
- **Redes & Infra:** Cisco, Huawei, Juniper, Roteamento, Switching, Monitoramento Syslog.

---

## 🔒 Segurança e Boas Práticas

Todos os projetos utilizam arquitetura desacoplada com variáveis de ambiente (`.env.example`), sem nenhuma chave ou dado confidencial versionado.

---

## 📬 Contato

- **Portfólio:** [sandymarques.github.io/talyson-projects](https://sandymarques.github.io/talyson-projects/)
- **GitHub:** [@SandyMarques](https://github.com/SandyMarques)
- **LinkedIn:** [linkedin.com/in/talysonmarques](https://www.linkedin.com/in/talysonmarques/)
- **Email:** talyson14marques@hotmail.com
