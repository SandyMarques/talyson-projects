# Guia: ajustes manuais no perfil do GitHub

Estes ajustes ficam nas configurações da conta e dos repositórios, fora do alcance de commits. Os textos abaixo estão prontos para copiar e colar. Todos seguem o currículo em PDF e o código dos repositórios.

Tempo estimado: 15 a 20 minutos.

---

## 1. README do perfil (feito)

O README do perfil já está publicado e é mantido no repositório [`SandyMarques/SandyMarques`](https://github.com/SandyMarques/SandyMarques), junto com o banner, os ícones e as capturas de tela. Para alterar o perfil, edite o `README.md` de lá.

---

## 2. Perfil (Settings → Public profile)

| Campo | Valor sugerido |
| :--- | :--- |
| **Name** | `Talyson Marques` |
| **Bio** (máx. 160) | `Automação de processos com Python e IA generativa (RAG, LLMs) · Analista na Accenture · Tecnólogo em Redes (SENAC-SP)` |
| **URL** | `https://sandymarques.github.io/talyson-projects/` |
| **Social accounts** | `https://www.linkedin.com/in/talysonmarques/` |
| **Company** | `Accenture Brasil` |
| **Location** | `Praia Grande, SP` |
| **Pronouns** | mantenha como está |

Em **Settings → Public profile → Contributions & activity**, deixe marcado **"Include private contributions on my profile"**. Assim, o trabalho em repositórios privados continua contando no gráfico, sem expor código.

A bio atual usa "Especialista em conectividade", o que pode soar como exagero para quem confere o currículo. A sugestão acima descreve o que os seus projetos mostram.

---

## 3. Descrição, site e tópicos de cada repositório

Na página de cada repositório, clique na engrenagem ⚙️ ao lado de **About**.

### `Assistente-IA-com-RAG`
- **Description:** `Chat com RAG que responde com base nos seus documentos (PDF, TXT, CSV, JSON) e cita as fontes. FastAPI, LangChain, ChromaDB e Docker.`
- **Topics:** `rag` `llm` `langchain` `chromadb` `fastapi` `python` `deepseek` `openai` `vector-database` `docker`

### `Automatizador-de-Planilhas-com-IA`
- **Description:** `Manipule planilhas Excel/CSV em português: a IA gera o código Pandas, executa em sandbox isolado e se autocorrige. Streamlit + DeepSeek.`
- **Topics:** `llm` `pandas` `streamlit` `excel` `automation` `python` `deepseek` `sandbox` `data-cleaning`

### `talyson-projects`
- **Description:** `Portfólio pessoal: projetos de automação e IA, blog e estudo de caso. Site estático publicado no GitHub Pages.`
- **Website:** marque **"Use your GitHub Pages website"**
- **Topics:** `portfolio` `github-pages` `tailwindcss` `javascript` `html` `blog`

### `curriculo`
- **Description:** `Currículo online de Talyson Marques: automação com Python, IA, redes e infraestrutura.`
- **Website:** marque **"Use your GitHub Pages website"**
- **Topics:** `curriculo` `resume` `github-pages` `html`

Em todos, desmarque **Packages** e **Deployments** se não forem usados. Isso deixa a lateral mais limpa.

---

## 4. Repositórios fixados (pins)

No perfil, use **Customize your pins** e fixe nesta ordem:

1. `Assistente-IA-com-RAG`
2. `Automatizador-de-Planilhas-com-IA`
3. `talyson-projects`
4. `curriculo`

O README do perfil (`SandyMarques`) não precisa ser fixado: ele já aparece no topo.

Se no futuro publicar outro projeto, ele pode entrar no lugar do `curriculo`. Antes de tornar público um repositório hoje privado, revise o histórico inteiro em busca de `.env`, chaves, senhas e dados de clientes. Apagar o arquivo em um commit novo **não** remove a chave do histórico. Se encontrar alguma, revogue a chave no provedor.

---

## 5. Integrar as melhorias nos repositórios dedicados

Os repositórios `Assistente-IA-com-RAG` e `Automatizador-de-Planilhas-com-IA` estavam com a versão de agosto do código, sem as correções de segurança feitas depois no `talyson-projects`. A versão atual foi enviada para o branch `claude/amazing-gauss-umxyo5` de cada um, com README novo, licença MIT e testes automáticos (GitHub Actions).

Para publicar: abra o repositório no GitHub, use **Compare & pull request** nesse branch, confira que o check **Testes** ficou verde e faça o merge na `main`.

---

## 6. Segurança da conta

- **Settings → Password and authentication:** ative a autenticação em duas etapas (2FA), se ainda não estiver ativa.
- **Settings → Code security** de cada repositório público: ative **Secret scanning** e **Push protection**. Assim o GitHub bloqueia um push que contenha uma chave de API.

---

## 7. Currículo em PDF

O PDF (`site/curriculo-talyson-marques.pdf`) traz **`github.com/talysonmarques`** no cabeçalho, mas o seu usuário é **`SandyMarques`**. Esse link leva a uma página que não é sua. Corrija no arquivo original do currículo e exporte o PDF de novo.

---

## 8. Hábitos que mantêm o perfil forte

- Atualize o README do perfil a cada 2 ou 3 meses, por exemplo com uma linha "construindo agora".
- Mantenha as mensagens de commit no padrão `feat:`, `fix:`, `docs:`, como já faz.
- Ao concluir um projeto, publique com README, prints ou GIF e um link de demonstração, se houver.
- Crie uma *release* (`v1.0.0`) quando um projeto estiver estável.
