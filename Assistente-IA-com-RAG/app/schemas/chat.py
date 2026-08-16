from typing import List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Representa uma mensagem no histórico da conversa."""
    role: str = Field(..., description="Papel da mensagem ('user' ou 'assistant')")
    content: str = Field(..., description="Conteúdo textual da mensagem")


class ChatRequest(BaseModel):
    """Modelo de entrada para requisição de chat com RAG."""
    query: str = Field(..., min_length=1, description="Pergunta ou instrução do usuário")
    history: Optional[List[ChatMessage]] = Field(default=[], description="Histórico de mensagens anteriores")
    top_k: Optional[int] = Field(default=None, ge=1, le=20, description="Número de documentos relevantes a recuperar")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Temperatura do modelo LLM")


class SourceDocument(BaseModel):
    """Metadados e trecho do documento de origem citado."""
    content: str = Field(..., description="Trecho textual relevante do documento")
    source: str = Field(..., description="Nome ou caminho do arquivo original")
    page: Optional[int] = Field(default=None, description="Número da página (quando aplicável)")
    chunk_id: Optional[int] = Field(default=None, description="Índice sequencial do chunk")
    score: Optional[float] = Field(default=None, description="Pontuação de relevância / similaridade")


class ChatResponse(BaseModel):
    """Resposta gerada pelo assistente RAG com fontes e estatísticas."""
    answer: str = Field(..., description="Resposta contextual gerada pela LLM")
    sources: List[SourceDocument] = Field(default=[], description="Lista de trechos citados como referência")
    sources_count: int = Field(default=0, description="Total de fontes utilizadas")
    model_used: str = Field(..., description="Nome do modelo LLM utilizado")
    execution_time_ms: float = Field(..., description="Tempo de processamento da consulta em milissegundos")
