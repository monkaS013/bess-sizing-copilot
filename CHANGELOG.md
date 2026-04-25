# Changelog

Todas as mudanças notáveis deste projeto serão documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

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
