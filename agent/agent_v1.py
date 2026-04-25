"""
agent_v1.py - Loop core do agente single Claude Sonnet com tool-use.

Uso programatico:

    from agent_v1 import Agent
    agent = Agent()
    resposta = agent.chat("Quero dimensionar um BESS para industria de 500 kW")
    print(resposta.texto)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

from prompts import SYSTEM_PROMPT
from tools import TOOL_DEFINITIONS, executar_tool


# Carrega .env da raiz do agent/ (mesma pasta do script)
load_dotenv(Path(__file__).resolve().parent / ".env")

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
MAX_TOKENS = 4096
MAX_ITERATIONS = 12  # safety net no loop tool-use


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    nome: str
    input: dict
    resultado: dict


@dataclass
class RespostaAgente:
    texto: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_input: int = 0
    tokens_output: int = 0
    iteracoes: int = 0
    erro: str | None = None


# ---------------------------------------------------------------------------
# Agente
# ---------------------------------------------------------------------------


class Agent:
    """
    Agente single. Mantem historico em memoria (use uma instancia por sessao).

    Para reset, instancie de novo.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY nao configurada. Crie um arquivo .env "
                "ou exporte a variavel de ambiente."
            )
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.system_prompt = system_prompt
        self.historico: list[dict[str, Any]] = []  # mensagens (user/assistant)

    def reset(self) -> None:
        self.historico = []

    def chat(self, mensagem_usuario: str) -> RespostaAgente:
        """
        Envia uma mensagem do usuario e processa o ciclo tool-use ate a
        resposta final. Acumula no historico.
        """
        self.historico.append({"role": "user", "content": mensagem_usuario})

        resposta = RespostaAgente(texto="")

        for i in range(MAX_ITERATIONS):
            resposta.iteracoes = i + 1
            try:
                api_response = self.client.messages.create(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    system=self.system_prompt,
                    tools=TOOL_DEFINITIONS,
                    messages=self.historico,
                )
            except Exception as e:
                resposta.erro = f"Erro na API: {type(e).__name__}: {e}"
                return resposta

            resposta.tokens_input += api_response.usage.input_tokens
            resposta.tokens_output += api_response.usage.output_tokens

            # Anexa a resposta do assistant ao historico (raw blocks)
            assistant_blocks = []
            text_chunks = []
            tool_uses = []
            for block in api_response.content:
                if block.type == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                    text_chunks.append(block.text)
                elif block.type == "tool_use":
                    assistant_blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    tool_uses.append(block)

            self.historico.append({"role": "assistant", "content": assistant_blocks})

            if api_response.stop_reason == "end_turn" or not tool_uses:
                # Fim do ciclo
                resposta.texto = "\n\n".join(text_chunks)
                return resposta

            # stop_reason == "tool_use" -> executa todas e devolve resultados
            tool_results = []
            for block in tool_uses:
                resultado = executar_tool(block.name, block.input)
                resposta.tool_calls.append(ToolCall(
                    nome=block.name,
                    input=block.input,
                    resultado=resultado,
                ))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(resultado, ensure_ascii=False),
                })

            self.historico.append({"role": "user", "content": tool_results})

        # Loop estourou
        resposta.erro = f"Limite de {MAX_ITERATIONS} iteracoes excedido."
        return resposta


# ---------------------------------------------------------------------------
# Smoke test (so se rodar como script com .env configurado)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Sanity check sem chamar API: imports OK, definicoes carregam.
    print(f"Modelo padrao: {DEFAULT_MODEL}")
    print(f"Tools registradas: {len(TOOL_DEFINITIONS)}")
    print("Para testar com chamada real, rode: streamlit run streamlit_app.py")
