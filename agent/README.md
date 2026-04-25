# BESS Sizing Copilot - Agent (Sprint 2)

Single agent Claude Sonnet 4.6 com as 13 funcoes de `bess-core` expostas como tools, interface web em Streamlit.

## Setup

```powershell
# 1. Criar venv (a partir da raiz do projeto)
cd "C:\Users\Vinicius\Desktop\Projeto HDT\agent"
python -m venv .venv
.venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar key
copy .env.example .env
# Abrir .env no editor e colar sua ANTHROPIC_API_KEY (criar em console.anthropic.com)

# 4. Rodar
streamlit run streamlit_app.py
```

A UI vai abrir em http://localhost:8501.

## Arquitetura

```
agent/
├── tools.py          Wrappers JSON dos calls de bess-core (6 tools)
├── perfis.py         Geradores de perfil de carga industrial/comercial
├── prompts.py        System prompt PT-BR do agente
├── agent_v1.py       Loop core: Claude SDK + tool-use
├── streamlit_app.py  UI: chat + visualizacao de tool calls
└── requirements.txt
```

## Como funciona

1. Usuario descreve o caso em linguagem natural ("indústria de 500 kW com pico...")
2. Agente faz perguntas de clarificacao (Discovery embutido)
3. Quando tem dados suficientes, chama as tools de `bess-core` em sequencia
4. Mostra cada tool call (input/output) na UI
5. Resume em proposta final estruturada (memorial + indicadores + SKU sugerido)

Sem PDF, sem regulatorio completo, sem multi-agente -- isso eh Sprint 4.
