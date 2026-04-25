# Changelog

Todas as mudanças notáveis deste projeto serão documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.6.1] — 2026-04-25

Validação contra caso real (Enel SP A4 Verde, REH ANEEL 3.477/2025) e correção do prompt para eliminar double-counting na decomposição de economia em peak shaving.

### Corrigido

- `agent/prompts.py` v0.5.2 — refatorado o bloco "Calculo de economia em peak shaving (BR)":
  - **Componente A (BASE)**: multa de ultrapassagem evitada — `2 × TUSD × kW excedente × meses`. Captura toda a economia da fatura de demanda quando o cliente já paga ultrapassagem.
  - **Componente B (BASE)**: spread ponta − fora-ponta na TE deslocada.
  - **Componente C (OPCIONAL)**: TUSD da demanda contratada — *só aplicável* se o cliente RENEGOCIAR o contrato (ex.: reduzir de 600 para 400 kW após instalar BESS). Não é fluxo automático.
  - Regra de ouro explicitada: nunca somar `TUSD × kW × 12` com `2× TUSD × kW × 12` — a multa já contém a TUSD multiplicada por 2 e representa o **adicional** pago hoje sobre o excedente.

### Adicionado

- `docs/CASO_REAL_INDUSTRIA_SP.md` — seção "Resultado da execução real (2026-04-25)" com:
  - Comparação do output do agente vs benchmark manual em 14 indicadores.
  - Score 6,5/7 (agente passa com folga; mínimo era 5/7).
  - Bônus entregues além do benchmark (BNDES Finem, qualificação ACL, caveat de perfil sintético).
  - Achados que motivaram correção em v0.5.2 (double-counting C1+C2 e premissa de descarga semanal).
- Benchmark recalculado no doc: economia esperada de **~R$ 150 k/ano** (apenas Componentes A + B), payback ~15 anos, VPL claramente negativo, veredicto inviável só com peak shaving.

### Observações operacionais

- Caso rodado no stack completo (frontend Next.js + backend FastAPI + InMemoryStorage), modelo `claude-sonnet-4-6`, prompts v0.5.1.
- Próximo passo: reexecutar este caso após v0.5.2 estar ativo para confirmar que economia cai para ~R$ 150 k/ano e veredicto continua inviável.

[0.6.1]: # "validacao real Enel SP + fix double-counting prompt"

## [0.6.0] — 2026-04-25

Sprint 3 — produto completo end-to-end. Single agent com tool-use, backend FastAPI, frontend Next.js e persistência Supabase opcional.

### Adicionado

#### Sprint 2 — Single agent (Claude SDK + tool-use)

- `agent/tools.py` — 8 wrappers JSON expondo todo o `bess-core` ao Claude. Cache de perfis em memória para evitar inflar contexto. Output do despacho sumarizado (não envia array 8760h ao LLM).
- `agent/agent_v1.py` — loop tool-use com Anthropic SDK. Max 12 iterações safety net. Persistência por sessão.
- `agent/perfis.py` — geradores sintéticos de perfil de carga (industrial semanal, comercial, FV).
- `agent/prompts.py` — system prompt PT-BR v0.5.1 com:
  - Decomposição de economia em 3 componentes (demanda + multa de ultrapassagem 2× + tarifa de energia deslocada).
  - Revenue stacking obrigatório em projetos inviáveis.
  - Resumo + confirmação antes da cadeia de tool calls.
  - Conta de luz como input ideal no discovery.
- `agent/streamlit_app.py` — UI dev com chat e expanders por tool call.

#### Sprint 3 Fase A — Backend FastAPI

- `agent/api_server.py` — 5 endpoints REST (`/api/health`, `/api/sessions`, `/api/chat`, `/api/sessions/{id}/historico`, `/api/sessions/{id}` DELETE) + Swagger auto-gerado em `/docs`.
- Sessões isoladas por instância de `Agent` em RAM (cache).
- CORS pré-configurado para Next.js (`:3000`) e Streamlit (`:8501`).
- Validação Pydantic automática em request bodies.

#### Sprint 3 Fase B — Frontend Next.js

- `frontend/` — Next.js 14 (App Router) + TypeScript + Tailwind + react-markdown + lucide-react.
- Chat UI com sidebar de status, expanders de tool calls (input/output JSON), markdown rendering, auto-scroll, auto-resize do textarea.
- API routes `/api/chat`, `/api/sessions`, `/api/health` como proxy server-side para FastAPI (esconde URL do backend).
- localStorage para persistir `session_id` entre reloads.
- Auto-recovery em sessão expirada: detecta erro 404, recria sessão silenciosamente, re-envia mensagem.

#### Sprint 3 Fase C — Persistência Supabase (opcional)

- `agent/storage.py` — interface `Storage` abstrata com 2 backends:
  - `InMemoryStorage` (default, retrocompatível).
  - `SupabaseStorage` (ativado por env vars `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`).
- `supabase/migrations/0001_init.sql` — schema idempotente com 3 tabelas (`sessoes_bess`, `mensagens`, `agente_logs`), índices, triggers de `atualizado_em`, RLS habilitada.
- `frontend/src/lib/supabase.ts` — client TS com `ensureUserId()` (auth anônimo Supabase OU UUID local) e graceful fallback.
- `docs/SETUP_SUPABASE.md` — passo-a-passo de criação de conta, projeto, migration SQL, env vars (10-15 min).

### Decisões de design

- **`postgrest>=0.16` em vez de `supabase>=2.7` umbrella**: o pacote completo puxa `storage3` → `pyiceberg` que tem extensão C exigindo MSVC no Windows. Como só usamos PostgREST para CRUD, eliminamos 5 dependências problemáticas.
- **Backend FastAPI separado em vez de Next.js puro**: mantém `bess-core` Python intacto, evita reescrita em TS, alinha com briefing original (Vercel + Railway).
- **Anonymous auth Supabase + `auth.uid()` por usuário**: zero fricção pro primeiro uso, sem login obrigatório, mantém RLS funcional.
- **Tool calls como JSONB em `mensagens` + replicadas em `agente_logs`**: visualização inline + analytics agregada.
- **`signInAnonymously` opcional**: se Supabase não configurado, frontend usa UUID local (`crypto.randomUUID`). Backend continua em InMemory. **Sistema funciona sem Supabase**.
- **Auto-recovery de sessão expirada no frontend**: usuário não percebe quando o backend reinicia (tipico em dev).

### Observações operacionais

- Stack rodando local em 2 terminais: `uvicorn api_server:app --port 8000` (backend) + `npm run dev` (frontend, `:3000`).
- Streamlit (`agent/streamlit_app.py`) continua disponível como alternativa de UI dev.
- Validado: pipeline end-to-end com Claude Sonnet 4.5, agente respondendo coerente, tool calls executando bess-core, frontend renderizando markdown e expanders.

### Limitações conhecidas (saída para versões futuras)

- **Sem JWT validation no backend** — backend confia em `X-User-Id` do header. Aceitável em dev, precisa de validação proper para produção pública.
- **Sem streaming SSE** — respostas chegam de uma vez, sem token-by-token.
- **Sem dark mode toggle** — CSS suporta `.dark`, mas falta o botão.
- **Sem Monte Carlo financeiro** — sensibilidade ±20% ainda é a única análise probabilística.

[0.6.0]: # "single agent + frontend + supabase opcional"

## [1.0.0] — 2026-04-24

Primeira versão estável: núcleo determinístico do BESS Sizing Copilot completo.

### Adicionado

#### Sprint 1.1 — Dimensionamento

- `dimensionar_peak_shaving(perfil_carga_horario, demanda_contratada_kw, ...)` — sizing para corte de demanda (REN 1.000/2021).
- `dimensionar_arbitragem(potencia_alvo_kw, duracao_descarga_h, ...)` — sizing para arbitragem temporal no ACL.
- `dimensionar_backup(carga_critica_kw, autonomia_h, ...)` — sizing para cargas críticas (NBR 13534), com defaults mais conservadores (DoD 0,95, reserva 20%).
- Dataclasses imutáveis: `DimensionamentoBESS`, `DimensionamentoArbitragem`, `DimensionamentoBackup`.

#### Sprint 1.2 — Despacho horário

- `simular_despacho_horario(perfil_carga_kw, capacidade_nominal_kwh, ...)` — simulação 8 760 h.
- Três estratégias: `peak_shaving`, `arbitragem` (greedy por percentil), `autoconsumo_hibrido`.
- Conservação de energia validada explicitamente: `E_c·η_c − E_d/η_d = ΔSoC·E_nom`.
- Limites de SoC traduzidos automaticamente em limites de potência admissível.
- Dataclass `ResultadoDespacho` com SoC, p_carga, p_descarga, p_grid, demanda residual, métricas agregadas.

#### Sprint 1.3 — Análise financeira

- `analisar_financeiro(capex_brl, opex_anual_brl, economia_anual_brl, ...)` — payback simples e descontado, TIR, VPL, LCOS.
- TIR via bissecção robusta (sem dependências externas, garantidamente convergente).
- Análise de sensibilidade ±20% em CAPEX, OPEX, economia e WACC (tornado chart).
- Modelo de fluxos de caixa com degradação anual da economia e inflação OPEX.
- Dataclasses `AnaliseFinanceira` e `SensibilidadeItem`.

#### Sprint 1.4 — Degradação SoH(t)

- `calcular_soh_anual(quimica, dod_medio, ciclos_ano, temperatura_celsius, ...)` — modelo aditivo calendárico + cíclico.
- Ajuste de Arrhenius para temperatura (a cada +10 °C, k_cal aproximadamente dobra).
- Ajuste de DoD na fadiga cíclica.
- Defaults calibrados contra fichas técnicas Tier 1 (Huawei LUNA2000-S0, CATL EnerOne) para LFP, NMC e LTO.
- EoL @ 80% SoH com interpolação linear.
- Dataclass `ResultadoDegradacao`.

#### Documentação

- `README.md` na raiz e em `bess-core/`.
- 5 memoriais técnicos em `docs/`:
  - `MEMORIAL_DIMENSIONAMENTO.md` (capítulo 2 do TCC)
  - `CASOS_VALIDACAO.md` (capítulo 4 do TCC)
  - `MEMORIAL_DESPACHO.md`
  - `MEMORIAL_FINANCEIRO.md` (capítulo 5 do TCC)
  - `MEMORIAL_DEGRADACAO.md`

#### Testes

- 141 testes em `pytest` cobrindo as 4 sprints:
  - 25 em `test_dimensionamento.py` (variantes + validações)
  - 22 em `casos_reais.py` (3 casos consolidados + comparações cruzadas)
  - 34 em `test_despacho.py` (3 estratégias + invariantes globais)
  - 27 em `test_financeiro.py` (identidades matemáticas + edge cases)
  - 33 em `test_degradacao.py` (Arrhenius + propriedades fundamentais)
- Suite roda em ~0,3 s.
- Tolerância 2% para validação contra cálculo manual.
- Identidades matemáticas testadas explicitamente: VPL@TIR=0, conservação de energia, monotonicidade do SoH.

### Decisões de design

- **Zero dependências externas além de `pytest`.** Tudo escrito em Python puro com `math` e `dataclasses`. Mantém a stack leve e o código auditável.
- **Heurístico vs LP no despacho.** Escolha greedy é provadamente ótima para peak shaving e autoconsumo. Para arbitragem é subótima vs LP, mas captura ~70-85% do valor com zero overhead de dependências. cvxpy fica como evolução opcional.
- **Bissecção para TIR.** Newton-Raphson é mais rápido mas pode falhar com múltiplas mudanças de sinal. Bissecção é garantidamente convergente.
- **Defaults Tier 1 vs literal do briefing.** Os valores de degradação cíclica do briefing original (0,025%/ciclo) corresponderiam a EoL de 1,8 anos para LFP — incompatível com qualquer datasheet real. Adotei valores calibrados contra Huawei/CATL e documentei a divergência.

### Limitações conhecidas (saída para próximas sprints)

- Sem Monte Carlo / análise probabilística (Sprint 1.3 deferido — segue diretriz §8 do briefing).
- LP via cvxpy para arbitragem ótima (evolução opcional Sprint 1.5+).
- Modelo de degradação linear até 80% SoH; knee point não modelado.
- Sem benefício fiscal de depreciação no financeiro (varia por regime tributário).
- Sem mistura de estratégias (peak shaving + arbitragem simultâneos) no despacho.
- Backup não simulado em horizonte 8 760 h (problema event-driven, fora do escopo).

[1.0.0]: # "primeira versão estável"
