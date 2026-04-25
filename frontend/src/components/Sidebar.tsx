"use client";

import { useState } from "react";
import { Battery, RefreshCw, AlertCircle, FileDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HealthResponse } from "@/lib/types";

type SidebarProps = {
  health: HealthResponse | null;
  healthError: string | null;
  sessionId: string | null;
  tokensInput: number;
  tokensOutput: number;
  hasMessages: boolean;
  onReset: () => void;
};

export function Sidebar({
  health,
  healthError,
  sessionId,
  tokensInput,
  tokensOutput,
  hasMessages,
  onReset,
}: SidebarProps) {
  const [pdfStatus, setPdfStatus] = useState<"idle" | "loading" | "error">(
    "idle"
  );
  const [pdfError, setPdfError] = useState<string | null>(null);

  async function baixarPDF() {
    if (!sessionId) return;
    setPdfStatus("loading");
    setPdfError(null);

    try {
      const res = await fetch(
        `/api/sessions/${sessionId}/relatorio-pdf`,
        { method: "POST" }
      );

      if (!res.ok) {
        let msg = `Falha HTTP ${res.status}`;
        try {
          const data = (await res.json()) as { error?: string };
          if (data.error) msg = data.error;
        } catch {
          // resposta nao era JSON
        }
        throw new Error(msg);
      }

      const blob = await res.blob();
      const filename =
        res.headers.get("X-Filename") ?? `BESS_Proposta_${sessionId.slice(0, 8)}.pdf`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      setPdfStatus("idle");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setPdfError(msg);
      setPdfStatus("error");
      // limpa erro depois de 5s
      setTimeout(() => {
        setPdfStatus("idle");
        setPdfError(null);
      }, 5000);
    }
  }

  const podeBaixar = !!sessionId && hasMessages && pdfStatus !== "loading";
  return (
    <aside className="w-72 shrink-0 border-r border-border bg-muted/30 flex flex-col">
      {/* Logo + nome */}
      <div className="px-4 py-5 border-b border-border">
        <div className="flex items-center gap-2">
          <Battery className="h-6 w-6 text-primary" strokeWidth={2.5} />
          <h1 className="text-lg font-bold tracking-tight">BESS Sizing Copilot</h1>
        </div>
        <p className="text-xs text-muted-foreground mt-1">Sprint 3 — Frontend Web</p>
      </div>

      {/* Status do backend */}
      <div className="px-4 py-4 border-b border-border space-y-2">
        <h2 className="text-xs uppercase tracking-wide text-muted-foreground font-semibold">
          Backend
        </h2>
        {healthError ? (
          <div className="flex items-start gap-2 text-xs text-destructive">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{healthError}</span>
          </div>
        ) : health ? (
          <>
            <Row label="Status" value={health.status} valueClass="text-green-600" />
            <Row label="Modelo" value={health.modelo} mono />
            <Row
              label="API key"
              value={health.api_key_configurada ? "configurada" : "ausente"}
              valueClass={
                health.api_key_configurada ? "text-green-600" : "text-destructive"
              }
            />
            <Row label="Sessoes ativas" value={String(health.sessoes_ativas)} />
            {(health as { storage?: string }).storage && (
              <Row
                label="Storage"
                value={(health as { storage: string }).storage.replace("Storage", "")}
                mono
              />
            )}
          </>
        ) : (
          <p className="text-xs text-muted-foreground">Carregando...</p>
        )}
      </div>

      {/* Sessao atual */}
      <div className="px-4 py-4 border-b border-border space-y-2">
        <h2 className="text-xs uppercase tracking-wide text-muted-foreground font-semibold">
          Sessao
        </h2>
        <Row
          label="ID"
          value={sessionId ? `${sessionId.slice(0, 8)}...` : "—"}
          mono
        />
        <Row label="Tokens entrada" value={tokensInput.toLocaleString("pt-BR")} />
        <Row label="Tokens saida" value={tokensOutput.toLocaleString("pt-BR")} />
      </div>

      {/* Acoes */}
      <div className="px-4 py-4 flex-1 flex flex-col gap-2">
        <button
          onClick={baixarPDF}
          disabled={!podeBaixar}
          title={
            !sessionId
              ? "Sem sessao ativa"
              : !hasMessages
              ? "Aguardando primeira resposta do agente"
              : "Baixar PDF da proposta executiva"
          }
          className={cn(
            "flex items-center justify-center gap-2",
            "w-full px-3 py-2 rounded-md",
            "text-sm font-medium",
            "bg-primary text-primary-foreground",
            "hover:bg-primary/90 transition-colors",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          {pdfStatus === "loading" ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Gerando...
            </>
          ) : (
            <>
              <FileDown className="h-4 w-4" />
              Baixar PDF da proposta
            </>
          )}
        </button>

        {pdfStatus === "error" && pdfError && (
          <div className="flex items-start gap-1.5 text-xs text-destructive bg-destructive/5 px-2 py-1.5 rounded">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span className="break-words">{pdfError}</span>
          </div>
        )}

        <button
          onClick={onReset}
          className={cn(
            "flex items-center justify-center gap-2",
            "w-full px-3 py-2 rounded-md",
            "text-sm font-medium",
            "bg-background border border-border",
            "hover:bg-muted transition-colors"
          )}
        >
          <RefreshCw className="h-4 w-4" />
          Nova conversa
        </button>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-border text-xs text-muted-foreground space-y-1">
        <p>
          Nucleo <span className="font-mono">bess-core v1.0.0</span>
        </p>
        <a
          href="https://github.com/monkaS013/bess-sizing-copilot"
          target="_blank"
          rel="noreferrer"
          className="text-primary hover:underline"
        >
          GitHub
        </a>
      </div>
    </aside>
  );
}

function Row({
  label,
  value,
  valueClass,
  mono,
}: {
  label: string;
  value: string;
  valueClass?: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-medium",
          mono && "font-mono",
          valueClass ?? "text-foreground"
        )}
      >
        {value}
      </span>
    </div>
  );
}
