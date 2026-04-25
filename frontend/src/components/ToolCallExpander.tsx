"use client";

import { useState } from "react";
import { Wrench, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ToolCall } from "@/lib/types";

export function ToolCallExpander({ toolCall }: { toolCall: ToolCall }) {
  const [open, setOpen] = useState(false);
  const temErro = "erro" in toolCall.resultado;

  return (
    <div
      className={cn(
        "rounded-lg border text-xs",
        temErro ? "border-destructive/30 bg-destructive/5" : "border-border bg-muted/40"
      )}
    >
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/60 rounded-lg transition-colors"
      >
        <Wrench className={cn("h-3.5 w-3.5", temErro && "text-destructive")} />
        <span className="font-mono font-medium">{toolCall.nome}</span>
        {temErro && (
          <span className="text-destructive font-semibold ml-auto mr-1">erro</span>
        )}
        <ChevronRight
          className={cn(
            "h-4 w-4 ml-auto transition-transform",
            temErro && "ml-1",
            open && "rotate-90"
          )}
        />
      </button>
      {open && (
        <div className="grid md:grid-cols-2 gap-3 px-3 py-3 border-t border-border">
          <div>
            <p className="font-semibold text-muted-foreground mb-1 uppercase text-[10px] tracking-wide">
              Input
            </p>
            <pre className="bg-background p-2 rounded text-[11px] overflow-x-auto">
              {JSON.stringify(toolCall.input, null, 2)}
            </pre>
          </div>
          <div>
            <p className="font-semibold text-muted-foreground mb-1 uppercase text-[10px] tracking-wide">
              Output
            </p>
            <pre className="bg-background p-2 rounded text-[11px] overflow-x-auto">
              {JSON.stringify(toolCall.resultado, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
