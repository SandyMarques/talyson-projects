"""Modelos de entrada e saída da API de chat com RAG.

Endurecimento de entrada (o cliente não pode influenciar as regras do sistema):

- `role` é um `Literal`: antes qualquer string era aceita, e `RAGService._convert_history`
  convertia `role="system"` em uma `SystemMessage` injetada ACIMA do prompt anti-alucinação.
  Qualquer cliente podia sobrescrever as instruções do sistema.
- `history` tem teto de itens e de tamanho por mensagem: sem isso o payload virava custo de
  tokens sem limite e vetor de abuso.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

#: Papéis aceitos do cliente. `system` fica de fora de propósito: o prompt de sistema é
#: propriedade do servidor.
AllowedRole = Literal["user", "assistant"]

#: Tetos de tamanho/payload (defesa contra abuso de custo e de memória).
MAX_HISTORY_MESSAGES = 50
MAX_MESSAGE_LENGTH = 8000
MAX_QUERY_LENGTH = 4000


class ChatMessage(BaseModel):
    """Representa uma mensagem no histórico da conversa."""

    role: AllowedRole = Field(
        ...,
        description="Papel da mensagem: 'user' ou 'assistant' (o papel 'system' é do servidor)",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=MAX_MESSAGE_LENGTH,
        description="Conteúdo textual da mensagem",
    )


class ChatRequest(BaseModel):
    """Modelo de entrada para requisição de chat com RAG."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=MAX_QUERY_LENGTH,
        description="Pergunta ou instrução do usuário",
    )
    history: Optional[List[ChatMessage]] = Field(
        default=None,
        max_length=MAX_HISTORY_MESSAGES,
        description=f"Histórico de mensagens (máximo {MAX_HISTORY_MESSAGES} itens)",
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description="Número de trechos relevantes a recuperar",
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Temperatura do modelo LLM",
    )
    min_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Distância máxima aceita na recuperação vetorial (menor = mais parecido). "
            "Trechos acima desse limite são descartados em vez de citados."
        ),
    )


class SourceDocument(BaseModel):
    """Metadados e trecho do documento de origem citado."""

    content: str = Field(..., description="Trecho textual relevante do documento")
    source: str = Field(..., description="Nome ou caminho do arquivo original")
    page: Optional[int] = Field(default=None, description="Número da página (quando aplicável)")
    chunk_id: Optional[int] = Field(default=None, description="Índice sequencial do chunk")
    #: Distância retornada pelo índice vetorial (L2 ao quadrado). Menor = mais relevante.
    #: NÃO é "similaridade": o frontend não deve convertê-la com `1 - score`.
    distance: Optional[float] = Field(
        default=None, description="Distância vetorial (menor = mais relevante)"
    )
    score: Optional[float] = Field(
        default=None,
        description="Alias legado de `distance`, mantido para compatibilidade do cliente web",
    )
    relevance_label: Optional[str] = Field(
        default=None, description="Rótulo qualitativo: alta, média ou baixa"
    )


class ChatResponse(BaseModel):
    """Resposta gerada pelo assistente RAG com fontes e estatísticas."""

    answer: str = Field(..., description="Resposta contextual gerada pela LLM")
    sources: List[SourceDocument] = Field(
        default_factory=list, description="Lista de trechos citados como referência"
    )
    sources_count: int = Field(default=0, description="Total de fontes utilizadas")
    model_used: str = Field(..., description="Nome do modelo LLM utilizado")
    execution_time_ms: float = Field(
        ..., description="Tempo de processamento da consulta em milissegundos"
    )
    discarded_count: int = Field(
        default=0,
        description="Trechos recuperados mas descartados por estarem acima do limiar de distância",
    )
