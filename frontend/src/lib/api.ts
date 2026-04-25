import type { ChatResponse, HealthResponse, SessaoCriadaResponse } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(
      data?.error ??
        data?.detail ??
        `Erro HTTP ${res.status}`
    );
  }
  return data as T;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export async function criarSessao(userId?: string): Promise<SessaoCriadaResponse> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-Id"] = userId;
  return request<SessaoCriadaResponse>("/api/sessions", {
    method: "POST",
    headers,
  });
}

export async function enviarMensagem(
  sessionId: string,
  mensagem: string
): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, mensagem }),
  });
}
