# Casos de Validação — BESS Sizing Copilot

**Versão:** 0.2.0 — Sprint 1.1 (encerrada)
**Suite de testes:** `bess-core/tests/casos_reais.py`
**Tolerância:** 2% sobre valores manualmente calculados
**Resultado:** 47/47 testes verdes

Este documento materializa o **Comando 2** do briefing — três casos reais com cálculo manual passo-a-passo e validação numérica via `pytest`. Reaproveitável como capítulo 4 do TCC ("Validação com 3 casos reais").

---

## Caso 1 — Peak Shaving Industrial 500 kW

### Cenário

Indústria de processo com perfil de carga semanal típico:

| Item | Valor |
|------|-------|
| Demanda contratada | 500 kW |
| Pico operacional | 650 kW |
| Duração do pico | 2 h/dia (14 h às 16 h) |
| Frequência | 5 dias úteis (seg–sex) |
| Carga base fim de semana | 300 kW (sem picos) |
| Tarifa de demanda | R$ 23,50/kW |
| Defaults | DoD=0,90; η_rt=0,92; reserva=0,10 |

### Cálculo manual

```
P_shave    = 650 − 500                                = 150,00 kW
E_util     = 150 × 2                                  = 300,00 kWh
η_d        = √0,92                                    ≈ 0,9592
E_nominal  = 300 / (0,90 × 0,9592) × 1,10             ≈ 382,18 kWh
P_nominal  = 150 / 0,9592 × 1,10                      ≈ 172,04 kW
C-rate     = 172,04 / 382,18                          ≈ 0,450 1/h
N_eventos  = 5 (um por dia útil na janela semanal)
```

### Resultado vs esperado

| Grandeza | Manual | Função | Δ |
|----------|--------|--------|---|
| P_shave | 150,00 kW | 150,00 kW | 0,00% |
| E_util | 300,00 kWh | 300,00 kWh | 0,00% |
| E_nominal | 382,18 kWh | 382,28 kWh | +0,03% |
| P_nominal | 172,04 kW | 172,02 kW | −0,01% |
| C-rate | 0,450 | 0,450 | 0,00% |
| Eventos | 5 | 5 | — |

**Status: PASS** (6 testes em `TestCaso1PeakShavingIndustrial500kW`)

### Interpretação técnica

Banco de média potência (C-rate ≈ 0,45). Compatível com SKU **Huawei LUNA2000-200KWH-2H1** (200 kWh × 2 racks = 400 kWh nominais), que entrega 100 kW por rack — soma 200 kW > 172 kW exigidos. Topologia AC-coupled recomendada para retrofit.

---

## Caso 2 — Arbitragem Mercado Livre 1 MW

### Cenário

Cliente do Ambiente de Contratação Livre (ACL) operando arbitragem temporal — compra em PLD baixo, vende em ponta:

| Item | Valor |
|------|-------|
| Potência alvo | 1 000 kW (1 MW) |
| Duração da descarga | 4 h (ESS de média duração) |
| Ciclos por dia | 1 |
| Defaults | DoD=0,90; η_rt=0,92; reserva=0,10 |

### Cálculo manual

```
E_util       = 1000 × 4                              = 4 000,00 kWh
η_d          = √0,92                                 ≈ 0,9592
E_nominal    = 4000 / (0,90 × 0,9592) × 1,10         ≈ 5 095,77 kWh
P_nominal    = 1000 / 0,9592 × 1,10                  ≈ 1 146,93 kW
C-rate       = 1146,93 / 5095,77                     ≈ 0,225 1/h
Throughput   = 4000 × 1 × 365                        = 1 460 000 kWh/ano
```

### Resultado vs esperado

| Grandeza | Manual | Função | Δ |
|----------|--------|--------|---|
| E_util | 4 000,00 kWh | 4 000,00 kWh | 0,00% |
| E_nominal | 5 095,77 kWh | 5 097,02 kWh | +0,02% |
| P_nominal | 1 146,93 kW | 1 146,83 kW | −0,01% |
| C-rate | 0,225 | 0,225 | 0,00% |
| Throughput anual | 1 460 000 kWh | 1 460 000 kWh | 0,00% |

**Status: PASS** (7 testes em `TestCaso2ArbitragemACL1MW`)

### Análise de garantia do fabricante

```
Throughput anual    = 1 460 MWh
E_nominal           = 5,1 MWh
Ciclos equivalentes = 1460 / 5,1 ≈ 286 ciclos/ano
```

Datasheet **Huawei LUNA2000-S0** garante 6 000 ciclos a 80% SoH → **vida útil ≈ 21 anos** com este uso. Coerente com horizonte típico de planta de geração (20–25 anos).

Para cenário de 2 ciclos/dia (mercados com janelas de PLD bem separadas), a garantia se exaure em ~10 anos — limite a observar na análise financeira.

---

## Caso 3 — Backup Hospitalar 100 kW

### Cenário

Hospital com cargas críticas Grupo 1 da NBR 13534 (CTI, centro cirúrgico, lab):

| Item | Valor |
|------|-------|
| Carga crítica | 100 kW |
| Autonomia exigida | 4 h |
| DoD (default backup) | 0,95 |
| Reserva técnica | 0,20 |
| η_rt | 0,92 |

**Defaults mais conservadores** que peak shaving por dois motivos: (1) em emergência, prioriza-se a continuidade da carga sobre a longevidade da célula → DoD agressivo; (2) o banco fica em standby por 10+ anos sem trocar células e precisa entregar a autonomia mesmo no fim de vida útil → reserva ampla.

### Cálculo manual

```
E_util       = 100 × 4                              = 400,00 kWh
η_d          = √0,92                                ≈ 0,9592
E_nominal    = 400 / (0,95 × 0,9592) × 1,20         ≈ 526,29 kWh
P_nominal    = 100 / 0,9592 × 1,20                  ≈ 125,11 kW
C-rate       = 125,11 / 526,29                      ≈ 0,238 1/h
```

### Resultado vs esperado

| Grandeza | Manual | Função | Δ |
|----------|--------|--------|---|
| E_util | 400,00 kWh | 400,00 kWh | 0,00% |
| E_nominal | 526,29 kWh | 526,77 kWh | +0,09% |
| P_nominal | 125,11 kW | 125,11 kW | 0,00% |
| C-rate | 0,238 | 0,238 | 0,00% |

**Status: PASS** (6 testes em `TestCaso3BackupHospitalar100kW`)

### Interpretação técnica

Banco de baixa potência específica (C-rate ≈ 0,24) — operação suave, ideal para emergência onde a célula não pode falhar por estresse térmico. Compatível com SKU **Huawei LUNA2000-S1** (100 kWh por rack, 50 kW de potência) configurado em **6 racks** para totalizar 600 kWh × 300 kW (sobrado em potência, justo em energia).

Conformidade regulatória mínima a observar (Sprint 4 — agente regulatório):
- NBR 5410 — aterramento e proteção
- NBR 13534 — instalações em estabelecimentos assistenciais de saúde
- IEC 62619 — segurança de baterias secundárias estacionárias
- IT-CBPMESP 49 — sistemas de detecção e supressão de incêndio

---

## Resumo Executivo

| Caso | E_util | E_nominal | P_nominal | C-rate | SKU Huawei |
|------|--------|-----------|-----------|--------|------------|
| 1 — Peak shaving 500 kW | 300 kWh | 382 kWh | 172 kW | 0,450 | LUNA2000-200KWH × 2 |
| 2 — Arbitragem 1 MW | 4 000 kWh | 5 097 kWh | 1 147 kW | 0,225 | LUNA2000-S0 × 25 |
| 3 — Backup 100 kW | 400 kWh | 527 kWh | 125 kW | 0,238 | LUNA2000-S1 × 6 |

### Validação cruzada entre casos

A suite `TestComparacoesEntreCasos` (3 testes) verifica invariantes que devem valer entre estratégias:

1. **Arbitragem 4 h tem C-rate menor que peak shaving 2 h** — banco de longa duração é menos agressivo. ✓
2. **Backup consome mais kWh nominais que arbitragem para mesma E_util** — DoD maior compensa menos que reserva maior. Razão = (0,90/0,95) × (1,20/1,10) ≈ 1,033. ✓
3. **Toda função retorna premissas auditáveis** — garante rastreabilidade para o agente Crítico (Sprint 4). ✓

---

## Como reproduzir

```powershell
cd "C:\Users\Vinicius\Desktop\Projeto HDT\bess-core"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest -v
```

Saída esperada:

```
============================== 47 passed in 0.16s ==============================
```

Para isolar apenas a suite de validação cruzada:

```powershell
pytest tests/casos_reais.py -v
```

---

## Próximos passos (saída da Sprint 1.1)

1. **Sprint 1.2 — Despacho 8760h.** Substituir o stub `bess_core.despacho.simular_despacho_horario` pela simulação SoC(t) horária com cvxpy para os três casos. Permite calcular ciclos efetivos vs equivalentes e perdas reais.
2. **Sprint 1.3 — Análise financeira.** Implementar `bess_core.financeiro.analisar_payback` (payback simples e descontado, TIR, VPL @ WACC 12%, LCOS).
3. **Sprint 1.4 — Degradação.** SoH(t) calendárico + cíclico para Huawei LUNA2000.
4. **Sprint 2 — Single agent.** Conectar funções como tools do Claude Sonnet via Agent SDK.
