import time
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
try:
    from langchain_deepseek import ChatDeepSeek
except ImportError:
    ChatDeepSeek = None
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, SourceDocument
from app.services.vector_store import VectorStoreManager

logger = get_logger(__name__)

RAG_SYSTEM_PROMPT = """Você é um assistente de inteligência artificial altamente capacitado, focado em responder dúvidas com base EXCLUSIVAMENTE nos documentos fornecidos como contexto.

INSTRUÇÕES OBRIGATÓRIAS:
1. Responda com base ESTRITAMENTE nas informações contidas na seção "CONTEXTO RECUPERADO DOS DOCUMENTOS".
2. Se a resposta para a pergunta não estiver contida no contexto fornecido, responda educadamente:
   "Com base nos documentos fornecidos, não encontrei informações suficientes para responder a esta pergunta."
   NUNCA invente informações, alucine fatos ou utilize conhecimento externo que não esteja presente no contexto.
3. Seja claro, conciso, organizado e profissional. Use formatação markdown (listas, tópicos, negrito) quando apropriado para tornar a leitura fluida.
4. Ao citar informações específicas, faça referência ao nome do documento e à página (se disponível).
5. Responda no mesmo idioma em que a pergunta foi feita (prioritariamente em Português).

---
CONTEXTO RECUPERADO DOS DOCUMENTOS:
{context}
"""


class RAGService:
    """Serviço responsável pela orquestração do fluxo RAG com LangChain, DeepSeek ou OpenAI."""

    def __init__(
        self,
        vector_store_manager: Optional[VectorStoreManager] = None,
        llm: Optional[BaseChatModel] = None,
    ):
        self.vector_store_manager = vector_store_manager or VectorStoreManager()
        if llm is not None:
            self.llm = llm
        elif settings.LLM_PROVIDER.lower() == "deepseek":
            if ChatDeepSeek is not None:
                self.llm = ChatDeepSeek(
                    model=settings.DEEPSEEK_MODEL,
                    api_key=settings.DEEPSEEK_API_KEY or "sk-dummy-key-for-init",
                    api_base=settings.DEEPSEEK_BASE_URL,
                    temperature=settings.TEMPERATURE,
                )
            else:
                self.llm = ChatOpenAI(
                    model=settings.DEEPSEEK_MODEL,
                    openai_api_key=settings.DEEPSEEK_API_KEY or "sk-dummy-key-for-init",
                    base_url=settings.DEEPSEEK_BASE_URL,
                    temperature=settings.TEMPERATURE,
                )
        else:
            self.llm = ChatOpenAI(
                openai_api_key=settings.OPENAI_API_KEY or "sk-dummy-key-for-init",
                model=settings.OPENAI_MODEL,
                temperature=settings.TEMPERATURE,
            )

        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", RAG_SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{question}"),
            ]
        )

    def _format_context(self, retrieved_docs: List[tuple]) -> str:
        """Formata os documentos recuperados em um bloco de texto estruturado para o prompt."""
        if not retrieved_docs:
            return "Nenhum documento relevante encontrado no banco vetorial."

        context_blocks = []
        for idx, (doc, score) in enumerate(retrieved_docs, start=1):
            source = doc.metadata.get("filename") or doc.metadata.get("source", "Documento")
            page = doc.metadata.get("page")
            page_info = f" | Página: {page}" if page is not None else ""
            block = (
                f"[Fonte {idx}] Documento: {source}{page_info}\n"
                f"Trecho:\n{doc.page_content.strip()}\n"
            )
            context_blocks.append(block)

        return "\n---\n".join(context_blocks)

    def _convert_history(self, history: List[ChatMessage]) -> List[Any]:
        """Converte a lista de mensagens do schema para mensagens do LangChain."""
        lc_messages = []
        for msg in history:
            if msg.role.lower() in ["user", "human"]:
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role.lower() in ["assistant", "ai"]:
                lc_messages.append(AIMessage(content=msg.content))
            elif msg.role.lower() == "system":
                lc_messages.append(SystemMessage(content=msg.content))
        return lc_messages

    async def answer_query(self, request: ChatRequest) -> ChatResponse:
        """
        Executa a recuperação de contexto vetorial e gera a resposta via LLM.
        """
        start_time = time.perf_counter()
        top_k = request.top_k or settings.TOP_K_RESULTS
        logger.info(f"Processando query RAG: '{request.query}' (top_k={top_k})")

        # Validação preventiva de API Key
        if not hasattr(self.llm, "response_text"):
            if settings.LLM_PROVIDER.lower() == "deepseek" and (not settings.DEEPSEEK_API_KEY or "dummy" in settings.DEEPSEEK_API_KEY):
                raise ValueError(
                    "A chave de API da DeepSeek não foi configurada! "
                    "Abra o arquivo .env e adicione sua chave em: DEEPSEEK_API_KEY=sk-..."
                )
            elif settings.LLM_PROVIDER.lower() == "openai" and (not settings.OPENAI_API_KEY or "dummy" in settings.OPENAI_API_KEY):
                raise ValueError(
                    "A chave de API da OpenAI não foi configurada! "
                    "Abra o arquivo .env e adicione sua chave em: OPENAI_API_KEY=sk-..."
                )

        # 1. Recuperação vetorial
        retrieved_items = self.vector_store_manager.similarity_search_with_score(
            query=request.query, k=top_k
        )

        # 2. Formatação do contexto
        context_str = self._format_context(retrieved_items)

        # 3. Montagem das fontes citadas
        sources: List[SourceDocument] = []
        for doc, score in retrieved_items:
            sources.append(
                SourceDocument(
                    content=doc.page_content,
                    source=doc.metadata.get("filename") or doc.metadata.get("source", "Desconhecido"),
                    page=doc.metadata.get("page"),
                    chunk_id=doc.metadata.get("chunk_id"),
                    score=round(float(score), 4) if score is not None else None,
                )
            )

        # 4. Histórico de conversas
        chat_history = self._convert_history(request.history or [])

        # 5. Execução do prompt na LLM
        prompt_value = self.prompt_template.invoke(
            {
                "context": context_str,
                "chat_history": chat_history,
                "question": request.query,
            }
        )

        # Se houver override de temperatura, instancia LLM dinamicamente se necessário
        active_llm = self.llm
        if request.temperature is not None and hasattr(self.llm, "temperature"):
            active_llm = self.llm.bind(temperature=request.temperature)

        response = await active_llm.ainvoke(prompt_value)
        answer_text = response.content if hasattr(response, "content") else str(response)

        execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        default_model = settings.DEEPSEEK_MODEL if settings.LLM_PROVIDER.lower() == "deepseek" else settings.OPENAI_MODEL
        model_name = getattr(self.llm, "model_name", getattr(self.llm, "model", default_model))

        logger.info(
            f"Resposta RAG gerada em {execution_time_ms}ms com {len(sources)} fontes citadas."
        )

        return ChatResponse(
            answer=answer_text,
            sources=sources,
            sources_count=len(sources),
            model_used=str(model_name),
            execution_time_ms=execution_time_ms,
        )
