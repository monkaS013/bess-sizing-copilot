"""
api_server.py - FastAPI envolvendo o agente para consumo via HTTP.

Endpoints:
  GET    /api/health                 -> status
  POST   /api/sessions               -> cria nova sessao
  POST   /api/chat                   -> envia mensagem na sessao
  GET    /api/sessions/{id}/historico-> historico de mensagens
  DELETE /api/sessions/{id}          -> encerra sessao

Persistencia (Sprint 3 Fase C):
  - Em RAM se SUPABASE_URL ausente.
  - No Supabase se SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY presentes.

A instancia do Agent (que tem o historico Anthropic) sempre fica em RAM
por sessao -- nao tem como serializar 'Agent' eficientemente, e o context
window do LLM eh refrescado a cada chamada de qualquer forma.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_v1 import Agent, RespostaAgente
from storage import MensagemRegistro, Storage, get_storage


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).resolve().parent / ".env")
API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8501",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8501",
]


# ---------------------------------------------------------------------------
# Storage + cache de Agents em memoria
# ---------------------------------------------------------------------------

_STORAGE: Storage = get_storage()
_AGENTS: dict[str, Agent] = {}


def _agent_para(session_id: str) -> Agent:
    """Retorna o Agent associado a sessao (cria se nao existe)."""
    if session_id not in _AGENTS:
        _AGENTS[session_id] = Agent()
    return _AGENTS[session_id]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Storage backend: {type(_STORAGE).__name__}")
    if not API_KEY:
        print("AVISO: ANTHROPIC_API_KEY ausente. /api/chat falhara.")
    else:
        print(f"API key carregada: {API_KEY[:15]}...")
        print(f"Modelo: {DEFAULT_MODEL}")
    yield
    _AGENTS.clear()


app = FastAPI(
    title="BESS Sizing Copilot API",
    version="0.2.0",
    description="Backend Python (FastAPI) com persistencia opcional Supabase.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*", "X-User-Id"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    versao: str
    modelo: str
    api_key_configurada: bool
    sessoes_ativas: int
    storage: str


class SessaoCriadaResponse(BaseModel):
    session_id: str
    criada_em: datetime


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="ID da sessao retornado por /api/sessions.")
    mensagem: str = Field(..., min_length=1)


class ToolCallDTO(BaseModel):
    nome: str
    input: dict
    resultado: dict


class ChatResponse(BaseModel):
    session_id: str
    texto: str
    tool_calls: list[ToolCallDTO] = Field(default_factory=list)
    tokens_input: int
    tokens_output: int
    iteracoes: int
    erro: str | None = None


class MensagemDTO(BaseModel):
    role: str
    content: str
    tool_calls: list[dict] = Field(default_factory=list)
    tokens_input: int = 0
    tokens_output: int = 0
    iteracoes: int = 1
    erro: str | None = None
    criado_em: datetime


class HistoricoResponse(BaseModel):
    session_id: str
    mensagens: list[MensagemDTO]
    tokens_total: dict
    criada_em: datetime
    atualizada_em: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        versao="0.2.0",
        modelo=DEFAULT_MODEL,
        api_key_configurada=bool(API_KEY),
        sessoes_ativas=_STORAGE.contar_sessoes_ativas(),
        storage=type(_STORAGE).__name__,
    )


@app.post("/api/sessions", response_model=SessaoCriadaResponse, status_code=201)
async def criar_sessao(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> SessaoCriadaResponse:
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY nao configurada no .env do agent/.",
        )
    try:
        sessao = _STORAGE.criar_sessao(usuario_id=x_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SessaoCriadaResponse(session_id=sessao.id, criada_em=sessao.criado_em)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    sessao = _STORAGE.obter_sessao(req.session_id)
    if not sessao:
        raise HTTPException(
            status_code=404,
            detail=f"Sessao {req.session_id} nao encontrada.",
        )

    # Persistir mensagem do usuario
    _STORAGE.adicionar_mensagem(MensagemRegistro(
        sessao_id=req.session_id,
        role="user",
        content=req.mensagem,
    ))

    agent = _agent_para(req.session_id)
    resposta: RespostaAgente = agent.chat(req.mensagem)

    # Persistir resposta do assistant (mesmo que com erro, pra debug)
    _STORAGE.adicionar_mensagem(MensagemRegistro(
        sessao_id=req.session_id,
        role="assistant",
        content=resposta.texto,
        tool_calls=[
            {"nome": tc.nome, "input": tc.input, "resultado": tc.resultado}
            for tc in resposta.tool_calls
        ],
        tokens_input=resposta.tokens_input,
        tokens_output=resposta.tokens_output,
        iteracoes=resposta.iteracoes,
        erro=resposta.erro,
    ))

    return ChatResponse(
        session_id=req.session_id,
        texto=resposta.texto,
        tool_calls=[
            ToolCallDTO(nome=tc.nome, input=tc.input, resultado=tc.resultado)
            for tc in resposta.tool_calls
        ],
        tokens_input=resposta.tokens_input,
        tokens_output=resposta.tokens_output,
        iteracoes=resposta.iteracoes,
        erro=resposta.erro,
    )


@app.get("/api/sessions/{session_id}/historico", response_model=HistoricoResponse)
async def historico(session_id: str) -> HistoricoResponse:
    sessao = _STORAGE.obter_sessao(session_id)
    if not sessao:
        raise HTTPException(
            status_code=404,
            detail=f"Sessao {session_id} nao encontrada.",
        )
    msgs = _STORAGE.listar_mensagens(session_id)
    return HistoricoResponse(
        session_id=sessao.id,
        mensagens=[
            MensagemDTO(
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls,
                tokens_input=m.tokens_input,
                tokens_output=m.tokens_output,
                iteracoes=m.iteracoes,
                erro=m.erro,
                criado_em=m.criado_em,
            )
            for m in msgs
        ],
        tokens_total={
            "input": sessao.tokens_input_total,
            "output": sessao.tokens_output_total,
        },
        criada_em=sessao.criado_em,
        atualizada_em=sessao.atualizado_em,
    )


@app.delete("/api/sessions/{session_id}", status_code=204)
async def encerrar_sessao(session_id: str) -> None:
    _STORAGE.encerrar_sessao(session_id)
    _AGENTS.pop(session_id, None)


@app.get("/")
async def root() -> dict:
    return {
        "service": "BESS Sizing Copilot API",
        "versao": "0.2.0",
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
