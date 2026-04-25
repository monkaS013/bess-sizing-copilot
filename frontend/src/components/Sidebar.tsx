"use client";

import { Battery, RefreshCw, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HealthResponse } from "@/lib/types";

type SidebarProps = {
  health: HealthResponse | null;
  healthError: string | null;
  sessionId: string | null;
  tokensInput: number;
  tokensOutput: number;
  onReset: () => void;
};

export function Sidebar({
  health,
  healthError,
  sessionId,
  tokensInput,
  tokensOutput,
  onReset,
}: SidebarProps) {
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
      <div className="px-4 py-4 flex-1 flex flex-col">
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
