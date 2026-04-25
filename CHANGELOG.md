# Changelog

Todas as mudanças notáveis deste projeto serão documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.8.0] — 2026-04-25

Sprint 4 Fases B + C — RAG da base regulatória + Monte Carlo financeiro. Agente passa a citar artigos com ancoragem em corpus indexado e oferece análise probabilística do VPL além do tornado ±20% determinístico.

### Adicionado

#### Sprint 4-C — Monte Carlo financeiro

- `bess-core/bess_core/financeiro.py`:
  - `ResultadoMonteCarlo` dataclass com P10/P25/P50/P75/P90 do VPL, média, desvio-padrão, mínimo/máximo, P(VPL > 0), histograma binned, distribuições usadas e seed.
  - `simulacao_monte_carlo(...)` com 10.000 iterações default, distribuições triangulares para CAPEX/OPEX/Economia (assimétricas para refletir realidade — CAPEX raramente cai mais que 15%, mas estoura facilmente 20%) e normal truncada para WACC.
  - Auxiliares `_triangular`, `_normal_truncada`, `_histograma_binned`, `_percentil` — todos puro Python, sem numpy.
- `bess-core/bess_core/__init__.py` — versão bumpada para 1.1.0, exporta `ResultadoMonteCarlo` e `simulacao_monte_carlo`.
- `bess-core/tests/test_monte_carlo.py` — 21 testes pytest cobrindo:
  - Reprodutibilidade com seed
  - Identidades estatísticas (P10 ≤ P25 ≤ P50 ≤ P75 ≤ P90, min/max envelopam percentis)
  - Probabilidades em [0, 1]
  - Monotonicidade econômica (CAPEX maior → menor viabilidade, etc.)
  - Histograma com soma == n_iteracoes
  - Validação de entrada
  - Casos degenerados (variância zero, projeto super viável, projeto inviável)
- `agent/tools.py` — nova tool `monte_carlo_financeiro` com helper `_classificar_risco()` que mapeia P(VPL>0) em rótulo verbal (BAIXO/MÉDIO/ALTO/MUITO ALTO).

#### Sprint 4-B — RAG da base regulatória

- `agent/regulamentos/` — pasta indexada com 4 arquivos `.md` curados:
  - `REN_1000_2021.md` — modalidades tarifárias, ultrapassagem (Art. 60), faturamento mínimo, ressarcimento, GD.
  - `LEI_14300_2022.md` — definições, SCEE, transição TUSD-fio B (2023-2029), modalidades de GD, limite de potência.
  - `NBR_13534.md` — Grupos 0/1/2 de criticidade hospitalar, autonomia mínima por grupo, dimensionamento típico.
  - `REH_3477_2025_ENEL_SP_A4_VERDE.md` — tarifas Enel SP A4 Verde verificadas no caso real, horário tarifário, implicações para BESS.
  - `README.md` com instruções para adicionar novos regulamentos (.md curado ou .pdf full-text).
- `agent/rag.py` — módulo de retrieval BM25:
  - `_chunkar()` particiona texto em chunks de ~200 tokens (md) ou ~350 (pdf) com overlap de 30 tokens.
  - `_tokenizar()` PT-BR via regex `[A-Za-z0-9À-ſ]+` + lowercase + remoção de acentos NFKD + filtragem de stopwords.
  - `consultar_regulamento(query, top_k=3, score_minimo=0.5)` retorna chunks com fonte e score.
  - Singleton `_INDICE_GLOBAL` evita reconstrução a cada query (~1s para 17 chunks atuais).
  - CLI `python rag.py rebuild` força reindexação (útil quando user adiciona PDF).
  - Demo embutido `python rag.py` roda 5 queries representativas.
- `agent/tools.py` — tool `consultar_base_regulatoria` com truncamento de resposta a 1500 chars/chunk (não estoura contexto do LLM).
- `agent/requirements.txt` — `rank_bm25>=0.2.2`, `pypdf>=4.0`.

#### Prompt — v0.5.3 → v0.6.0

- Nova seção "Ancoragem regulatória (RAG via consultar_base_regulatoria)" com **regra de ouro**: "voce NAO inventa numeros de artigos, valores tarifarios ou prazos legais. SEMPRE chame consultar_base_regulatoria ANTES de citar."
- Nova seção "Análise probabilística (Monte Carlo)" com 3 cenários explícitos para uso da tool: VPL central próximo de zero, pedido explícito do cliente, projeto de alto valor (CAPEX > R$ 5M).
- Fluxo padrão atualizado: `... → analisar_financeiro → [monte_carlo_financeiro se incerteza alta] → match_sku_huawei → proposta executiva final`.
- Conformidade ampliada: NBR 13534 explicitamente listada além de NBR 16690/5410.

### Decisões de design

- **BM25 keyword over embeddings semânticos**: zero deps pesadas (sem torch/transformers), sem download de modelo (~100 MB), tempo de boot <1s. Para corpus pequeno e curado, BM25 é tão bom quanto embeddings em precisão. Upgrade para embeddings fica como Sprint 4-B v2 se necessário.
- **Markdown curado em vez de PDFs full-text**: precisão semântica maior em corpus pequeno. PDFs oficiais ANEEL/Planalto são longos e ruidosos — geram chunks tangenciais que diluem BM25. Markdown curado tem só os artigos-chave, com tags de retrieval explícitas. PDFs continuam suportados (pypdf) caso usuário queira indexar full-text depois.
- **Distribuições triangulares assimétricas**: CAPEX(0.85, 1.0, 1.20) reflete que cotação direta com Tier 1 raramente bate -15%, mas overrun de obra estoura +20% facilmente. Economia(0.70, 1.0, 1.15) — upside limitado (regulamentação pode mudar contra), downside maior (tarifa pode cair).
- **Stopwords PT-BR mínimas inline**: lista de ~30 palavras de altíssima frequência. Sem deps externas (NLTK/spaCy). "art" e "artigo" estão na lista porque são frequentes demais em regulamentos e prejudicam o IDF.
- **Truncamento de chunk a 1500 chars no output da tool**: chunks maiores estouram contexto do LLM em queries paralelas. Trade-off aceitável porque o agente recebe múltiplos chunks — se o primeiro não for suficiente, ele tem 2 mais.

### Observações operacionais

- Smoke test do RAG no sandbox: 17 chunks indexados de 4 arquivos .md curados em <1s. Queries representativas retornam top-3 corretamente:
  - "hospital UTI" → NBR_13534 (score 4.62)
  - "Lei 14300 transicao TUSD" → LEI_14300_2022 (score 4.82)
  - "Enel SP A4 Verde" → REH_3477_2025 (score 3.99)
- Smoke test do Monte Carlo no sandbox: bloqueado por sync degradado do mount Linux. Validação local pelo usuário pendente.
- Stack precisa de `pip install -r requirements.txt` para puxar `rank_bm25` e `pypdf` antes de subir o uvicorn.

### Limitações conhecidas (Sprint 4-B v2 / 4-C v2)

- **RAG keyword-only**: não captura sinônimos automaticamente ("multa de demanda" vs "penalidade de ultrapassagem"). Upgrade para embeddings (sentence-transformers multilingue) está documentado em `agent/regulamentos/README.md` como evolução opcional.
- **NBR 13534 paywall**: corpus contém apenas pontos públicos sobre Grupo 1 (UTI/centro cirúrgico) compilados de manuais Eletrobras PROCEL. Texto integral da norma exige licença ABNT.
- **Atualizações tarifárias manuais**: REHs novas precisam ser adicionadas como .md curado quando ANEEL publicar reajuste. Automação de scraping fica para Sprint 5.
- **Monte Carlo sem correlação entre variáveis**: CAPEX e OPEX são amostrados independentemente, mas na prática são correlacionados (cotação alta tende a vir com manutenção cara). Pode ser refinado com matriz de correlação em Sprint 4-C v2.

[0.8.0]: # "Monte Carlo financeiro + RAG da base regulatoria"

## [0.7.0] — 2026-04-25

Sprint 4 Fase A — Geração de PDF da proposta executiva. Cliente final pode baixar relatório técnico-comercial profissional via botão no sidebar.

### Adicionado

#### Backend Python

- `agent/pdf_generator.py` — módulo de geração de PDF baseado em `reportlab` (Platypus) + `markdown-it-py`:
  - `gerar_proposta_pdf(mensagens, session_id, modelo)` recebe a lista de mensagens da sessão, identifica heuristicamente a última proposta executiva do agente (preferência: ≥400 chars com headings/tabelas) e renderiza para PDF.
  - Layout corporativo HDT Energy + BESS Sizing Copilot: header com faixa azul-marinho (#0B2545), accent laranja (#E76F00), footer paginado com session_id + timestamp + modelo.
  - Parser markdown → Platypus suporta H1-H3, parágrafos, listas (bulleted/numbered), tabelas GFM com header destacado, inline (bold/italic/code/link).
  - Página final automática com "Sobre esta proposta" (premissas e ressalvas regulatórias gerais).
  - Smoke test embedded: `python pdf_generator.py` gera `_smoketest_proposta.pdf` (validado: 5,2 KB / 2 páginas).
- `agent/api_server.py` — novo endpoint `POST /api/sessions/{session_id}/relatorio-pdf`:
  - Busca sessão e mensagens via `Storage`, chama `gerar_proposta_pdf`, retorna PDF binary.
  - Filename gerado: `BESS_Proposta_<YYYYMMDD_HHMM>_<id8>.pdf` no header `Content-Disposition` e `X-Filename`.
  - 404 se sessão não existe, 400 se vazia ou sem proposta detectável, 500 em falha de geração.
  - CORS atualizado com `expose_headers=["Content-Disposition"]` para o frontend ler o filename.
- `agent/requirements.txt` — novas dependências: `reportlab>=4.0`, `markdown-it-py>=3.0`.

#### Frontend Next.js

- `frontend/src/app/api/sessions/[id]/relatorio-pdf/route.ts` — proxy server-side que retransmite o PDF binário do FastAPI mantendo `Content-Disposition` e `X-Filename`. Trata erros JSON do backend e retorna mensagem útil.
- `frontend/src/components/Sidebar.tsx` — novo botão **"Baixar PDF da proposta"**:
  - Habilitado quando há ao menos 1 resposta do agente na sessão (`hasMessages`).
  - Estados: `idle` (botão azul ativo), `loading` (spinner + texto "Gerando..."), `error` (mensagem inline em vermelho com auto-clear após 5s).
  - Cria URL.createObjectURL do blob, cria `<a download>` e dispara click — trigger nativo do browser.
- `frontend/src/app/page.tsx` — passa `hasMessages` para o `Sidebar`.

#### Configuração

- `.gitignore` — exclui `agent/_smoketest_*.pdf`, `agent/relatorios/`, `frontend/.next/`, `frontend/node_modules/`, `frontend/out/`.

### Decisões de design

- **Backend gera PDF, não frontend**: reportlab tem layout determinístico, fontes embutidas e renderização consistente cross-platform. jsPDF/react-pdf no browser teriam variações de fonte por OS.
- **Markdown da proposta como input, não JSON estruturado**: o agente já produz markdown estruturado por design do prompt v0.5.2. Reaproveitar isso evita uma rodada extra de tool call (importante dado os limites de rate limit no Tier Free Anthropic).
- **Proposta final apenas, não session transcript**: PDF é entregável para cliente — limpo, executivo. Histórico fica disponível via `/api/sessions/{id}/historico` se precisar de auditoria.
- **Heurística para identificar proposta**: preferência por última mensagem do assistant com ≥400 caracteres E (headings markdown OU tabelas). Fallback para última resposta independente de tamanho. Robusto a respostas curtas vs longas.
- **`reportlab` em vez de `weasyprint`**: reportlab é Python puro (sem deps de sistema), enquanto weasyprint requer `pango`/`cairo` que pesa em deploy. Trade-off: weasyprint é mais "HTML-CSS-like", mas reportlab dá controle pixel-perfect via Platypus.

### Observações operacionais

- Smoke test do backend OK: PDF de 2 páginas gerado com sucesso a partir de markdown sample (proposta industrial peak shaving).
- Para testar end-to-end: reiniciar uvicorn (após `pip install -r requirements.txt` para puxar `reportlab` + `markdown-it-py`), recarregar frontend, rodar uma conversa até proposta final, clicar **"Baixar PDF da proposta"** no sidebar.

### Limitações conhecidas (próximas iterações Sprint 4)

- **Sem suporte a imagens no markdown** — agente não gera imagens hoje, então não é gap real.
- **Sem logos vetoriais** — branding atual é texto-only. Adicionar PNG/SVG da HDT requer pequena mudança em `_desenhar_header_footer`.
- **Sem template alternativo "transcript completo"** — apenas modo "proposta executiva". Pode ser adicionado em v0.7.1 se necessário.
- **Geração síncrona** — para sessões muito grandes pode haver latência perceptível. Streaming/async fica pra próximas iterações.

[0.7.0]: # "PDF export da proposta executiva"

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
