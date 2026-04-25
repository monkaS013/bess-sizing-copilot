export type ToolCall = {
  nome: string;
  input: Record<string, unknown>;
  resultado: Record<string, unknown>;
};

export type ChatResponse = {
  session_id: string;
  texto: string;
  tool_calls: ToolCall[];
  tokens_input: number;
  tokens_output: number;
  iteracoes: number;
  erro: string | null;
};

export type SessaoCriadaResponse = {
  session_id: string;
  criada_em: string;
};

export type HealthResponse = {
  status: string;
  versao: string;
  modelo: string;
  api_key_configurada: boolean;
  sessoes_ativas: number;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  tokensInput?: number;
  tokensOutput?: number;
  timestamp: string;
};
