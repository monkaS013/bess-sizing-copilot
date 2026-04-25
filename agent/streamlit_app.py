"""
streamlit_app.py - UI do agente single Claude Sonnet.

Rode com:
    streamlit run streamlit_app.py

Requer .env com ANTHROPIC_API_KEY na pasta agent/.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

# Garantir que tools/agent_v1 sao importaveis quando rodando do streamlit
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from agent_v1 import Agent, RespostaAgente


# ---------------------------------------------------------------------------
# Config da pagina
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="BESS Sizing Copilot",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Estado da sessao
# ---------------------------------------------------------------------------

if "agent" not in st.session_state:
    st.session_state.agent = None
if "mensagens_ui" not in st.session_state:
    st.session_state.mensagens_ui = []  # lista de {role, content, tool_calls?}
if "tokens_total" not in st.session_state:
    st.session_state.tokens_total = {"input": 0, "output": 0}


def reiniciar_conversa():
    st.session_state.agent = None
    st.session_state.mensagens_ui = []
    st.session_state.tokens_total = {"input": 0, "output": 0}


# ---------------------------------------------------------------------------
# Sidebar: configuracao + reset + status
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🔋 BESS Sizing Copilot")
    st.caption("Sprint 2 — Single agent")
    st.divider()

    api_key_env = os.getenv("ANTHROPIC_API_KEY")
    if api_key_env:
        st.success(f"✓ API key carregada (**{api_key_env[:15]}...**)")
    else:
        st.error("⚠️ ANTHROPIC_API_KEY ausente. Crie .env em agent/")
        st.stop()

    modelo = st.text_input(
        "Modelo",
        value=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        help="Override opcional do modelo Claude.",
    )

    st.divider()
    st.subheader("Sessão")

    if st.button("🔄 Nova conversa", use_container_width=True):
        reiniciar_conversa()
        st.rerun()

    st.metric("Tokens entrada", f"{st.session_state.tokens_total['input']:,}")
    st.metric("Tokens saída",  f"{st.session_state.tokens_total['output']:,}")

    st.divider()
    st.caption(
        "Núcleo `bess-core` v1.0.0  \n"
        "8 tools expostas  \n"
        "Repo: github.com/monkaS013/bess-sizing-copilot"
    )


# ---------------------------------------------------------------------------
# Inicializacao do agente (uma vez por sessao)
# ---------------------------------------------------------------------------

if st.session_state.agent is None:
    try:
        st.session_state.agent = Agent(model=modelo)
    except RuntimeError as e:
        st.error(str(e))
        st.stop()


# ---------------------------------------------------------------------------
# Render do historico de mensagens
# ---------------------------------------------------------------------------

st.title("BESS Sizing Copilot")
st.caption(
    "Descreva o caso em linguagem natural. O agente fará perguntas, "
    "calculará o sizing e proporá uma solução técnica."
)

for msg in st.session_state.mensagens_ui:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                with st.expander(f"🔧 {tc['nome']}", expanded=False):
                    col_in, col_out = st.columns(2)
                    with col_in:
                        st.caption("Input")
                        st.json(tc["input"])
                    with col_out:
                        st.caption("Output")
                        st.json(tc["resultado"])
        st.markdown(msg["content"])


# ---------------------------------------------------------------------------
# Input do usuario
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Descreva o caso ou faça uma pergunta..."):
    # Mostrar mensagem do usuario
    st.session_state.mensagens_ui.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Processar resposta
    with st.chat_message("assistant"):
        with st.spinner("Calculando..."):
            resposta: RespostaAgente = st.session_state.agent.chat(prompt)

        if resposta.erro:
            st.error(f"❌ {resposta.erro}")
        else:
            # Tool calls colapsados
            if resposta.tool_calls:
                for tc in resposta.tool_calls:
                    with st.expander(f"🔧 {tc.nome}", expanded=False):
                        col_in, col_out = st.columns(2)
                        with col_in:
                            st.caption("Input")
                            st.json(tc.input)
                        with col_out:
                            st.caption("Output")
                            st.json(tc.resultado)

            # Texto da resposta
            st.markdown(resposta.texto)

            # Atualizar metrica de tokens
            st.session_state.tokens_total["input"] += resposta.tokens_input
            st.session_state.tokens_total["output"] += resposta.tokens_output

            # Adicionar ao historico UI
            st.session_state.mensagens_ui.append({
                "role": "assistant",
                "content": resposta.texto,
                "tool_calls": [
                    {"nome": tc.nome, "input": tc.input, "resultado": tc.resultado}
                    for tc in resposta.tool_calls
                ],
            })

    st.rerun()
