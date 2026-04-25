"use client";

import { User, Bot } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import type { Message } from "@/lib/types";
import { ToolCallExpander } from "./ToolCallExpander";

export function ChatMessage({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "max-w-4xl mx-auto px-4 py-4",
        isUser ? "" : "bg-muted/30"
      )}
    >
      <div className="flex gap-4">
        <div
          className={cn(
            "shrink-0 h-8 w-8 rounded-full flex items-center justify-center",
            isUser ? "bg-primary text-primary-foreground" : "bg-foreground text-background"
          )}
        >
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-muted-foreground mb-2">
            {isUser ? "Voce" : "BESS Sizing Copilot"}
            {message.tokensOutput !== undefined && message.tokensOutput > 0 && (
              <span className="ml-2 font-mono text-[10px]">
                {message.tokensInput?.toLocaleString("pt-BR")} in /{" "}
                {message.tokensOutput.toLocaleString("pt-BR")} out
              </span>
            )}
          </p>

          {/* Tool calls aparecem ANTES do texto da resposta */}
          {message.toolCalls && message.toolCalls.length > 0 && (
            <div className="space-y-1.5 mb-3">
              {message.toolCalls.map((tc, i) => (
                <ToolCallExpander key={i} toolCall={tc} />
              ))}
            </div>
          )}

          {/* Conteudo */}
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose-bess">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
