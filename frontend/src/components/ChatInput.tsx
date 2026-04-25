"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type ChatInputProps = {
  onSend: (mensagem: string) => void;
  disabled: boolean;
  loading: boolean;
};

export function ChatInput({ onSend, disabled, loading }: ChatInputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize do textarea conforme o usuario digita
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [text]);

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled || loading) return;
    onSend(trimmed);
    setText("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-border bg-background">
      <div className="max-w-4xl mx-auto px-4 py-3">
        <div
          className={cn(
            "flex items-end gap-2 rounded-xl border border-border",
            "bg-muted/30 focus-within:bg-background",
            "focus-within:border-primary focus-within:ring-1 focus-within:ring-primary",
            "transition-colors"
          )}
        >
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              disabled
                ? "Aguardando backend..."
                : "Descreva o caso ou faça uma pergunta... (Enter para enviar, Shift+Enter quebra linha)"
            }
            disabled={disabled}
            rows={1}
            className={cn(
              "flex-1 resize-none bg-transparent",
              "px-4 py-3 text-sm",
              "outline-none",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
          />
          <button
            onClick={handleSubmit}
            disabled={disabled || loading || !text.trim()}
            className={cn(
              "shrink-0 m-2 p-2 rounded-lg",
              "bg-primary text-primary-foreground",
              "hover:opacity-90 transition-opacity",
              "disabled:opacity-30 disabled:cursor-not-allowed"
            )}
            aria-label="Enviar mensagem"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground mt-2 text-center">
          O agente nao calcula -- toda matematica vai pelo nucleo Python deterministico.
        </p>
      </div>
    </div>
  );
}
