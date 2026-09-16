# Regras de Desenvolvimento e Auditoria do Repositório

> `AGENTS.md` é a fonte da verdade destas regras. O `GEMINI.md` mantém o mesmo conteúdo para agentes Gemini — ao alterar um, replique no outro e mantenha os dois idênticos.

Este arquivo define diretrizes e protocolos permanentes que o agente de IA DEVE seguir estritamente ao trabalhar neste projeto.

---

## 🗂️ Escopo do Repositório

| Caminho | Descrição | Verificação |
| :--- | :--- | :--- |
| `site/` | Portfólio estático (HTML único por página, Tailwind + Lucide via CDN), publicado no GitHub Pages. | Parse de HTML, `node --check` no JS embutido, existência de links/arquivos |
| `Assistente-IA-com-RAG/` | Backend FastAPI + LangChain + ChromaDB. | `pytest` |
| `Automatizador-de-Planilhas-com-IA/` | App Streamlit + Pandas + DeepSeek. | `pytest` |
| `motion-design/` | Skill de referência de motion design (sem build/testes). | Inspeção |

---

## 🛡️ Protocolo Obrigatório de Auto-Auditoria e Segurança Pré-Push

Toda vez que uma nova funcionalidade, correção de bug, refatoração ou alteração for implementada, o agente **NÃO DEVE** considerar a tarefa concluída, propor commits ou realizar `push` sem antes executar rigorosamente este checklist de auto-auditoria.

---

### 1. Verificação Funcional e Testes Automatizados
- **Execução de Testes (Python):** Identificar o submódulo/projeto afetado e rodar a suíte de testes automatizados existente (`pytest` em `Assistente-IA-com-RAG`, `Automatizador-de-Planilhas-com-IA`).
- **Portfólio (`site/`):** Alterações em HTML/JS DÉVEM ser validadas por:
  - parse de HTML válido (sem tags não fechadas);
  - `node --check` no JavaScript embutido, quando alterado;
  - conferência de que todo link/arquivo interno referenciado existe (`Test-Path`).
  - Não aceitar implementação-fachada: botão de download que não baixa, formulário que não usa `mailto:` ou toggle de tema inerte.
- **Validação de Sintaxe e Compilação:** Verificar se não há imports ausentes, erros de tipagem óbvios ou dependências não declaradas no `requirements.txt` / `package.json`.
- **Auto-Correção:** Se qualquer teste ou checagem falhar, corrigir a causa raiz antes de prosseguir. Nunca ignorar testes quebrados.

---

### 2. Auditoria de Segurança Básica e Prevenção de Vazamentos
- **Zero Hardcoded Secrets (Crítico):**
  - NUNCA inserir no código nem commitar chaves de API (`sk-...`, tokens, senhas, certificados, credenciais de banco).
  - Qualquer novo parâmetro de configuração ou segredo DEVE ser lido de variáveis de ambiente (`os.getenv`, Pydantic Settings, etc.).
  - Todo novo segredo deve ser documentado exclusivamente em `.env.example` com valor fictício / placeholder.
  - Verificar ativamente se o arquivo `.env` está no `.gitignore` e não foi adicionado ao stage do Git.
- **Sanitização e Segurança de Código:**
  - Evitar concatenações inseguras em comandos de sistema (`os.system`, `subprocess` sem sanitização).
  - Prevenir vulnerabilidades óbvias de injeção (SQL, Path Traversal em upload/download de arquivos, `eval` arbitrário).
- **Auditoria de Dependências:**
  - Caso novas dependências sejam adicionadas, verificar se são pacotes oficiais e confiáveis.
  - Sempre que viável, rodar auditoria rápida (`pip audit` ou `npm audit`).

---

### 3. Higiene do Git e Arquivos Temporários
- **Inspeção de Status (`git status`):**
  - Conferir quais arquivos foram modificados ou adicionados.
  - Garantir que NENHUM arquivo temporário, cache (`__pycache__`, `.pytest_cache`), logs, banco vetorial local (`data/chroma/`), uploads locais ou artefatos de coordenação (`.teamwork/`) sejam rastreados pelo Git.
- **Commits Claros:** Mensagens de commit devem ser concisas e semânticas (ex: `feat: ...`, `fix: ...`, `refactor: ...`, `test: ...`, `docs: ...`).

---

### 4. Relatório Obrigatório de Auditoria na Conclusão
Ao concluir qualquer implementação, a resposta final do agente DEVE incluir um sumário objetivo da verificação realizada, no seguinte formato:

```markdown
### 🛡️ Auditoria de Segurança & Integridade Pré-Push
- [x] **Testes Automatizados:** [Resultados dos testes executados / validação de sintaxe]
- [x] **Varredura de Credenciais:** Nenhuma chave, segredo ou token exposto no código.
- [x] **Higiene do Git & .env:** Sem arquivos sensíveis ou temporários rastreados.
- [x] **Status Geral:** Aprovado para commit/push.
```
