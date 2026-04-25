"use client";

import { useEffect, useRef, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { ChatMessage } from "@/components/ChatMessage";
import { ChatInput } from "@/components/ChatInput";
import { criarSessao, enviarMensagem, fetchHealth } from "@/lib/api";
import { ensureUserId } from "@/lib/supabase";
import type { HealthResponse, Message } from "@/lib/types";

const STORAGE_KEY = "bess.session_id";

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [tokensInput, setTokensInput] = useState(0);
  const [tokensOutput, setTokensOutput] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Bootstrap: carrega health e cria sessao se necessario
  useEffect(() => {
    let mounted = true;

    (async () => {
      try {
        const h = await fetchHealth();
        if (!mounted) return;
        setHealth(h);
        setHealthError(null);
      } catch (e) {
        if (!mounted) return;
        setHealthError(
          e instanceof Error
            ? e.message
            : "Backend FastAPI nao respondeu. Rode: uvicorn api_server:app --port 8000"
        );
        return;
      }

      // Garante user identificavel (anonymous Supabase auth ou UUID local)
      let uid: string;
      try {
        uid = await ensureUserId();
        if (!mounted) return;
        setUserId(uid);
      } catch (e) {
        if (!mounted) return;
        setError(
          "Falha ao identificar usuario: " +
          (e instanceof Error ? e.message : String(e))
        );
        return;
      }

      // Tenta reusar sessao do localStorage. Se falhar, cria nova.
      const cached = localStorage.getItem(STORAGE_KEY);
      if (cached) {
        setSessionId(cached);
        return;
      }
      try {
        const s = await criarSessao(uid);
        if (!mounted) return;
        setSessionId(s.session_id);
        localStorage.setItem(STORAGE_KEY, s.session_id);
      } catch (e) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : "Falha ao criar sessao.");
      }
    })();

    return () => {
      mounted = false;
    };
  }, []);

  // Auto-scroll para o final ao adicionar mensagem
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading]);

  const handleSend = async (text: string) => {
    if (!sessionId) {
      setError("Sem session_id. Reinicie a conversa.");
      return;
    }

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setError(null);

    try {
      let resp;
      try {
        resp = await enviarMensagem(sessionId, text);
      } catch (e) {
        // Detecta sessao expirada (FastAPI reiniciou e perdeu InMemoryStorage):
        // cria nova sessao automaticamente e re-envia a mensagem do usuario.
        const msg = e instanceof Error ? e.message : String(e);
        const sessaoExpirada = /nao encontrada|not found/i.test(msg);
        if (!sessaoExpirada) throw e;

        // Recria sessao silenciosamente
        const uid = userId ?? (await ensureUserId());
        const nova = await criarSessao(uid);
        setSessionId(nova.session_id);
        localStorage.setItem(STORAGE_KEY, nova.session_id);
        resp = await enviarMensagem(nova.session_id, text);
      }
      if (resp.erro) {
        setError(resp.erro);
        return;
      }
      const assistantMsg: Message = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: resp.texto,
        toolCalls: resp.tool_calls,
        tokensInput: resp.tokens_input,
        tokensOutput: resp.tokens_output,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setTokensInput((t) => t + resp.tokens_input);
      setTokensOutput((t) => t + resp.tokens_output);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro de comunicacao.");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    setMessages([]);
    setTokensInput(0);
    setTokensOutput(0);
    setError(null);
    localStorage.removeItem(STORAGE_KEY);
    try {
      const uid = userId ?? (await ensureUserId());
      const s = await criarSessao(uid);
      setSessionId(s.session_id);
      localStorage.setItem(STORAGE_KEY, s.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao resetar.");
    }
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        health={health}
        healthError={healthError}
        sessionId={sessionId}
        tokensInput={tokensInput}
        tokensOutput={tokensOutput}
        onReset={handleReset}
      />

      <main className="flex-1 flex flex-col">
        {/* Mensagens */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <EmptyState />
          ) : (
            messages.map((m) => <ChatMessage key={m.id} message={m} />)
          )}
          {loading && (
            <div className="max-w-4xl mx-auto px-4 py-4 bg-muted/30">
              <div className="flex gap-4">
                <div className="shrink-0 h-8 w-8 rounded-full bg-foreground text-background flex items-center justify-center text-xs">
                  ...
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span className="animate-pulse">Pensando, calculando, encadeando tools</span>
                  <span className="inline-flex gap-0.5">
                    <span className="animate-bounce">.</span>
                    <span className="animate-bounce [animation-delay:0.1s]">.</span>
                    <span className="animate-bounce [animation-delay:0.2s]">.</span>
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Erro inline */}
        {error && (
          <div className="border-t border-destructive/30 bg-destructive/10 px-4 py-2">
            <p className="max-w-4xl mx-auto text-xs text-destructive">
              <strong>Erro:</strong> {error}
            </p>
          </div>
        )}

        {/* Input */}
        <ChatInput
          onSend={handleSend}
          disabled={!sessionId || !!healthError}
          loading={loading}
        />
      </main>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="h-full flex items-center justify-center px-4">
      <div className="max-w-2xl text-center space-y-4">
        <h2 className="text-2xl font-semibold tracking-tight">
          Dimensione um BESS em linguagem natural
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Descreva sua industria, perfil de carga, demanda contratada e
          objetivo. O agente faz a entrevista, calcula sizing, simula
          despacho, projeta degradacao e analisa viabilidade financeira.
        </p>
        <div className="grid sm:grid-cols-2 gap-3 text-left mt-6">
          <ExampleCard text="Industria com 500 kW contratados, pico de 650 kW por 2h em 5 dias uteis. Tarifa 23,50 R$/kW. Em SP." />
          <ExampleCard text="Hospital com 100 kW de cargas criticas. Preciso de 4h de autonomia para o CTI." />
          <ExampleCard text="Cliente livre com 1 MW de banco para arbitragem temporal no ACL. Descarga de 4h." />
          <ExampleCard text="Tenho 500 kWp de FV ja instalado. Quero adicionar BESS para deslocar consumo da ponta." />
        </div>
      </div>
    </div>
  );
}

function ExampleCard({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground hover:bg-muted/60 transition-colors">
      &ldquo;{text}&rdquo;
    </div>
  );
}
