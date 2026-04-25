"""
storage.py - Camada de persistencia de sessoes/mensagens.

Duas implementacoes:
  - InMemoryStorage: sessoes em memoria (default, MVP local)
  - SupabaseStorage: persistencia via supabase-py (Sprint 3 Fase C)

A escolha eh automatica:
  - SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY presentes -> SupabaseStorage
  - Caso contrario -> InMemoryStorage

Convencao: o storage NAO conhece o Agent (instancias permanecem em memoria
por sessao). Ele so persiste *historico* e *metricas* para auditoria.
"""

from __future__ import annotations

import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


@dataclass
class SessaoMeta:
    id: str
    usuario_id: str | None
    status: str
    criado_em: datetime
    atualizado_em: datetime
    tokens_input_total: int = 0
    tokens_output_total: int = 0


@dataclass
class MensagemRegistro:
    sessao_id: str
    role: str  # 'user' | 'assistant'
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tokens_input: int = 0
    tokens_output: int = 0
    iteracoes: int = 1
    erro: str | None = None
    criado_em: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class Storage(ABC):
    @abstractmethod
    def criar_sessao(self, usuario_id: str | None = None) -> SessaoMeta: ...

    @abstractmethod
    def obter_sessao(self, sessao_id: str) -> SessaoMeta | None: ...

    @abstractmethod
    def adicionar_mensagem(self, msg: MensagemRegistro) -> None: ...

    @abstractmethod
    def listar_mensagens(self, sessao_id: str) -> list[MensagemRegistro]: ...

    @abstractmethod
    def encerrar_sessao(self, sessao_id: str) -> None: ...

    @abstractmethod
    def contar_sessoes_ativas(self) -> int: ...


# ---------------------------------------------------------------------------
# InMemoryStorage (default, sem dependencias externas)
# ---------------------------------------------------------------------------


class InMemoryStorage(Storage):
    """Persistencia em RAM. Perde tudo ao reiniciar o servidor."""

    def __init__(self) -> None:
        self._sessoes: dict[str, SessaoMeta] = {}
        self._mensagens: dict[str, list[MensagemRegistro]] = {}

    def criar_sessao(self, usuario_id: str | None = None) -> SessaoMeta:
        agora = datetime.now(timezone.utc)
        sid = str(uuid.uuid4())
        sessao = SessaoMeta(
            id=sid,
            usuario_id=usuario_id,
            status="ativa",
            criado_em=agora,
            atualizado_em=agora,
        )
        self._sessoes[sid] = sessao
        self._mensagens[sid] = []
        return sessao

    def obter_sessao(self, sessao_id: str) -> SessaoMeta | None:
        return self._sessoes.get(sessao_id)

    def adicionar_mensagem(self, msg: MensagemRegistro) -> None:
        if msg.sessao_id not in self._mensagens:
            raise ValueError(f"sessao {msg.sessao_id} nao existe.")
        self._mensagens[msg.sessao_id].append(msg)
        sessao = self._sessoes[msg.sessao_id]
        sessao.atualizado_em = datetime.now(timezone.utc)
        sessao.tokens_input_total += msg.tokens_input
        sessao.tokens_output_total += msg.tokens_output

    def listar_mensagens(self, sessao_id: str) -> list[MensagemRegistro]:
        return list(self._mensagens.get(sessao_id, []))

    def encerrar_sessao(self, sessao_id: str) -> None:
        self._sessoes.pop(sessao_id, None)
        self._mensagens.pop(sessao_id, None)

    def contar_sessoes_ativas(self) -> int:
        return len(self._sessoes)


# ---------------------------------------------------------------------------
# SupabaseStorage (Sprint 3 Fase C)
# ---------------------------------------------------------------------------


class SupabaseStorage(Storage):
    """
    Persistencia via Supabase Postgres usando supabase-py.

    Usa SERVICE_ROLE_KEY no backend para bypass de RLS quando necessario
    (insert em nome do usuario via X-User-Id no header). RLS continua
    valendo para o cliente JS do frontend (ANON_KEY + JWT do
    signInAnonymously).
    """

    def __init__(self, url: str, service_role_key: str) -> None:
        # Usamos postgrest direto (sub-pacote leve do supabase) em vez do
        # umbrella 'supabase' para evitar deps pesadas (storage3 + pyiceberg
        # exigem MSVC no Windows). postgrest cobre tudo que precisamos:
        # CRUD nas tabelas via PostgREST.
        try:
            from postgrest import SyncPostgrestClient  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "postgrest nao instalado. Rode: pip install postgrest"
            ) from e
        self._client: Any = SyncPostgrestClient(
            base_url=f"{url.rstrip('/')}/rest/v1",
            headers={
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
            },
        )

    def criar_sessao(self, usuario_id: str | None = None) -> SessaoMeta:
        if usuario_id is None:
            raise ValueError(
                "Supabase exige usuario_id. Configure auth anonymous no "
                "frontend e passe X-User-Id no header."
            )
        resp = (
            self._client.from_("sessoes_bess")
            .insert({
                "usuario_id": usuario_id,
                "status": "ativa",
            })
            .execute()
        )
        row = resp.data[0]
        return self._row_to_sessao(row)

    def obter_sessao(self, sessao_id: str) -> SessaoMeta | None:
        resp = (
            self._client.from_("sessoes_bess")
            .select("*")
            .eq("id", sessao_id)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        return self._row_to_sessao(resp.data[0])

    def adicionar_mensagem(self, msg: MensagemRegistro) -> None:
        # 1. Persistir mensagem
        self._client.from_("mensagens").insert({
            "sessao_id": msg.sessao_id,
            "role": msg.role,
            "content": msg.content,
            "tool_calls": msg.tool_calls,
            "tokens_input": msg.tokens_input,
            "tokens_output": msg.tokens_output,
            "iteracoes": msg.iteracoes,
            "erro": msg.erro,
        }).execute()

        # 2. Atualizar totais na sessao
        if msg.tokens_input or msg.tokens_output:
            atual = self.obter_sessao(msg.sessao_id)
            if atual is not None:
                self._client.from_("sessoes_bess").update({
                    "tokens_input_total":  atual.tokens_input_total + msg.tokens_input,
                    "tokens_output_total": atual.tokens_output_total + msg.tokens_output,
                }).eq("id", msg.sessao_id).execute()

        # 3. Logar tool calls (auditoria)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                self._client.from_("agente_logs").insert({
                    "sessao_id": msg.sessao_id,
                    "agente": "single",
                    "tool_chamada": tc.get("nome", ""),
                    "tool_input": tc.get("input", {}),
                    "tool_output": tc.get("resultado", {}),
                }).execute()

    def listar_mensagens(self, sessao_id: str) -> list[MensagemRegistro]:
        resp = (
            self._client.from_("mensagens")
            .select("*")
            .eq("sessao_id", sessao_id)
            .order("criado_em", desc=False)
            .execute()
        )
        return [self._row_to_mensagem(r) for r in resp.data]

    def encerrar_sessao(self, sessao_id: str) -> None:
        self._client.from_("sessoes_bess").update({
            "status": "encerrada"
        }).eq("id", sessao_id).execute()

    def contar_sessoes_ativas(self) -> int:
        resp = (
            self._client.from_("sessoes_bess")
            .select("id", count="exact")
            .eq("status", "ativa")
            .execute()
        )
        return resp.count or 0

    @staticmethod
    def _row_to_sessao(row: dict) -> SessaoMeta:
        return SessaoMeta(
            id=row["id"],
            usuario_id=row.get("usuario_id"),
            status=row["status"],
            criado_em=_parse_dt(row["criado_em"]),
            atualizado_em=_parse_dt(row["atualizado_em"]),
            tokens_input_total=row.get("tokens_input_total", 0) or 0,
            tokens_output_total=row.get("tokens_output_total", 0) or 0,
        )

    @staticmethod
    def _row_to_mensagem(row: dict) -> MensagemRegistro:
        return MensagemRegistro(
            sessao_id=row["sessao_id"],
            role=row["role"],
            content=row["content"],
            tool_calls=row.get("tool_calls") or [],
            tokens_input=row.get("tokens_input", 0) or 0,
            tokens_output=row.get("tokens_output", 0) or 0,
            iteracoes=row.get("iteracoes", 1) or 1,
            erro=row.get("erro"),
            criado_em=_parse_dt(row["criado_em"]),
        )


def _parse_dt(value: Any) -> datetime:
    """Parse ISO 8601 string ou pass-through datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Supabase devolve com 'Z' que datetime.fromisoformat aceita 3.11+;
        # normaliza pra '+00:00' por compat com 3.10.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError(f"datetime esperado, recebeu {type(value)}")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_storage() -> Storage:
    """
    Retorna InMemoryStorage ou SupabaseStorage baseado em env vars.

    Para usar Supabase, defina:
      SUPABASE_URL=https://<project-ref>.supabase.co
      SUPABASE_SERVICE_ROLE_KEY=<service_role_key>

    Caso contrario, retorna InMemoryStorage (perde dados ao reiniciar).
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if url and key:
        try:
            return SupabaseStorage(url, key)
        except Exception as e:
            print(f"[storage] Falha ao conectar Supabase ({e}). Usando memoria.")
    return InMemoryStorage()
