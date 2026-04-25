# BESS Sizing Copilot — Frontend (Sprint 3, Fase B)

Next.js 14 (App Router) + TypeScript + Tailwind. Chat UI consumindo o backend FastAPI da Fase A.

## Stack

- Next.js 14.2 App Router
- TypeScript 5.6
- Tailwind 3.4
- React 18.3
- `react-markdown` para renderizar resposta do assistant
- `lucide-react` para icones

## Setup

```powershell
cd "C:\Users\Vinicius\Desktop\Projeto HDT\frontend"

# 1. Instalar dependencias (uma vez)
pnpm install

# 2. Configurar URL do backend (uma vez)
copy .env.local.example .env.local
# Edite .env.local se o backend rodar em porta diferente de 8000.

# 3. Rodar
pnpm dev
```

UI abre em http://localhost:3000.

## Pre-requisito

O backend FastAPI (Fase A) precisa estar no ar:

```powershell
# Em outro terminal:
cd "C:\Users\Vinicius\Desktop\Projeto HDT\agent"
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn api_server:app --reload --port 8000
```

## Arquitetura

```
Browser (localhost:3000)
   |
   | fetch /api/*
   v
Next.js Server (localhost:3000/api/*)
   |
   | fetch BESS_API_URL  (http://localhost:8000/api/*)
   v
FastAPI (localhost:8000)
   |
   | call agent_v1.Agent
   v
Anthropic Claude Sonnet 4.5
   |
   | tool_use
   v
bess-core (Python)
```

O frontend nunca conversa direto com FastAPI — sempre via `/api/*` proxy do Next.js. Isso esconde a URL do backend, permite logging server-side e simplifica o deploy (uma URL so do ponto de vista do navegador).

## Estrutura de arquivos

```
frontend/
├── package.json
├── tsconfig.json
├── next.config.mjs
├── tailwind.config.ts
├── postcss.config.mjs
├── .env.local.example
└── src/
    ├── app/
    │   ├── layout.tsx          Root layout (PT-BR, metadata)
    │   ├── globals.css         Tailwind base + CSS vars + estilos prose
    │   ├── page.tsx            Chat UI (componente principal)
    │   └── api/
    │       ├── health/route.ts     Proxy GET para FastAPI
    │       ├── sessions/route.ts   Proxy POST para criar sessao
    │       └── chat/route.ts       Proxy POST para enviar mensagem
    ├── components/
    │   ├── Sidebar.tsx             Status backend + sessao + reset
    │   ├── ChatMessage.tsx         User/Assistant + markdown + tool calls
    │   ├── ToolCallExpander.tsx    Card colapsavel com input/output JSON
    │   └── ChatInput.tsx           Textarea auto-resize + send button
    └── lib/
        ├── api.ts                  fetch wrapper (criarSessao, enviarMensagem, fetchHealth)
        ├── types.ts                Shapes do FastAPI (TS types)
        └── utils.ts                cn() helper + formatBRL/formatNumber
```

## Sessao em localStorage

O `session_id` retornado por `POST /api/sessions` fica em `localStorage` sob a chave `bess.session_id`. Recarregando a pagina, retoma a mesma sessao (que persiste em memoria no FastAPI por enquanto — Fase C migra para Supabase).

"Nova conversa" no sidebar limpa o localStorage e cria nova sessao.

## Comandos uteis

```powershell
pnpm dev          # rodar em desenvolvimento (hot reload)
pnpm build        # production build
pnpm start        # rodar build de producao
pnpm lint         # eslint
pnpm type-check   # tsc --noEmit (so checa types)
```

## Limitacoes conhecidas

1. **Sem streaming** — respostas chegam de uma vez. Streaming SSE fica para Fase B.1 (opcional).
2. **Sem dark mode toggle** — o CSS suporta `.dark` mas nao expoe botao. Adicionar shadcn `<ThemeToggle />` se quiser.
3. **Markdown basico** — `react-markdown` sem plugins. Tabelas funcionam graças ao GFM mas falta `remark-gfm` para checkbox lists.
4. **localStorage como unica persistencia** — Fase C adiciona Supabase para auth + historico cross-device.
5. **Sem indicacao visual de tool em execucao** — mostra spinner generico, nao sabe qual tool esta rodando agora.

## Deploy futuro (Fase D)

- Frontend: Vercel (`vercel --prod`)
- Backend: Railway com Docker (FastAPI + agent + bess-core)
- Variavel `BESS_API_URL` aponta para a URL do Railway

## Licenca

Proprietary — HDT Energy.
