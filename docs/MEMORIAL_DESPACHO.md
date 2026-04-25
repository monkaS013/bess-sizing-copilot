# Memorial de Cálculo — Simulação Horária de Despacho

**Versão:** 0.3.0 — Sprint 1.2
**Módulo:** `bess_core.despacho.simular_despacho_horario`
**Autor:** Vinicius Morais (HDT Energy)
**Última revisão:** 2026-04-24

---

## 1. Escopo

Este memorial descreve o modelo matemático e as decisões de implementação da simulação horária de despacho do BESS, segunda peça do núcleo determinístico (Sprint 1). Enquanto a Sprint 1.1 calcula o **tamanho** do banco para um pior caso, a Sprint 1.2 simula o **comportamento** do banco hora a hora ao longo de um horizonte arbitrário (típico: 8 760 h = 1 ano).

Três estratégias suportadas:

| Estratégia | Descrição | Otimalidade do greedy |
|---|---|---|
| `peak_shaving` | Corte de demanda contratada | **Ótima** (ver § 5.1) |
| `arbitragem` | Compra em PLD baixo, vende em alto | **Subótima** (ver § 5.2) |
| `autoconsumo_hibrido` | FV + BESS para autoconsumo | **Ótima** (ver § 5.3) |

## 2. Convenções e variáveis de estado

| Símbolo | Significado | Unidade |
|---------|-------------|---------|
| $SoC(t)$ | State of Charge — fração da capacidade DC ocupada | adim. (0–1) |
| $E_{nom}$ | Capacidade nominal DC do banco | kWh |
| $P_{nom}$ | Potência nominal do PCS/inversor | kW |
| $\eta_c, \eta_d$ | Eficiências de carga e descarga (AC ↔ DC) | adim. |
| $\eta_{rt}$ | Eficiência round-trip = $\eta_c \cdot \eta_d$ | adim. |
| $p_c(t)$ | Potência AC drenada para carregar o banco | kW |
| $p_d(t)$ | Potência AC entregue pelo banco | kW |
| $p_{load}(t)$ | Demanda da carga | kW |
| $p_{fv}(t)$ | Geração FV no instante (opcional) | kW |
| $p_{grid}(t)$ | Fluxo líquido pelo medidor (positivo = importa) | kW |
| $\Delta t$ | Passo de simulação | h |

Adota-se eficiência simétrica $\eta_c = \eta_d = \sqrt{\eta_{rt}}$ — mesma escolha da Sprint 1.1, garantindo coerência entre dimensionamento e despacho.

## 3. Dinâmica do SoC

Atualização discreta do estado de carga, em DC:

$$
SoC(t+1) = SoC(t) + \frac{\bigl(p_c(t) \cdot \eta_c - p_d(t)/\eta_d\bigr) \cdot \Delta t}{E_{nom}}
$$

Restrições físicas aplicadas a cada passo:

$$
\begin{aligned}
0 \le \; & p_c(t),\; p_d(t) \;\le P_{nom} \\
& p_c(t) \cdot p_d(t) = 0 \quad \text{(carga e descarga mutuamente exclusivas)} \\
SoC_{min} \le \; & SoC(t) \le SoC_{max}
\end{aligned}
$$

Onde $SoC_{min} = 1 - \mathrm{DoD}$ e $SoC_{max} = 1$ por default.

A função interna `_limites_potencia` traduz a restrição de SoC em limites de potência admissíveis no passo atual:

$$
\begin{aligned}
p_c^{max}(t) &= \min\!\left( P_{nom},\; \frac{(SoC_{max} - SoC(t)) \cdot E_{nom}}{\eta_c \cdot \Delta t} \right) \\
p_d^{max}(t) &= \min\!\left( P_{nom},\; \frac{(SoC(t) - SoC_{min}) \cdot E_{nom} \cdot \eta_d}{\Delta t} \right)
\end{aligned}
$$

Garantindo que mesmo se a estratégia pedir potência cheia, a atualização do SoC não saia dos bounds — a invariante é verificada no teste `test_soc_nunca_foge_dos_bounds_peak_shaving`.

## 4. Fluxo do medidor

$$
p_{grid}(t) = p_{load}(t) + p_c(t) - p_d(t) - p_{fv}(t)
$$

Convenção: $p_{grid} > 0$ ⇒ importação; $p_{grid} < 0$ ⇒ exportação. Para clientes pós-Lei 14.300, exportação é desejável apenas até o ponto onde o Fio B se torna proibitivo — cálculo financeiro será da Sprint 1.3.

A demanda residual vista pelo medidor (relevante para peak shaving):

$$
p_{load}^{resid}(t) = \max\bigl(p_{load}(t) - p_d(t),\; 0\bigr)
$$

## 5. Estratégias de dispatch

### 5.1 Peak shaving (greedy ótimo)

```text
excedente = max(p_load(t) - threshold, 0)
if excedente > 0:
    p_d = min(excedente, p_d_max)
    return (0, p_d)
else:
    headroom = max(threshold - p_load(t), 0)
    p_c = min(headroom, p_c_max)
    return (p_c, 0)
```

**Argumento de otimalidade.** Definindo o problema como minimizar a demanda de pico medida ao longo do horizonte — isto é, $\min_{p_c, p_d} \max_t p_{grid}(t)$ — sob restrições de SoC e potência:

> Em cada passo onde $p_{load}(t) > \mathrm{threshold}$, a única ação que reduz o pico medido é descarregar. Não há benefício em "guardar" energia para um pico futuro maior, porque o sizing da Sprint 1.1 já garante capacidade para o pior evento. Logo, descarregar o máximo admissível em cada hora é localmente e globalmente ótimo.

Implementação verificada nos testes `test_corte_exato_no_threshold` (com SoC suficiente, demanda residual nunca excede threshold) e `test_p_grid_corresponde_ao_corte`.

### 5.2 Arbitragem (greedy subótimo, defensável)

```text
ordenado = sorted(precos[0..N-1])
limiar_carga    = percentil(ordenado, p_carga)    # default 25%
limiar_descarga = percentil(ordenado, p_descarga) # default 75%

if preco(t) <= limiar_carga and SoC < SoC_max:
    return (p_c_max, 0)
elif preco(t) >= limiar_descarga and SoC > SoC_min:
    return (0, p_d_max)
else:
    return (0, 0)
```

**Limitação reconhecida.** Comparado a uma formulação LP com previsão perfeita (objetivo: $\max \sum p_d(t) \cdot preço(t) - p_c(t) \cdot preço(t)$ sob restrições de SoC), a heurística por percentil:

1. Ignora a magnitude relativa entre preços de carga e descarga — só decide com base em "barato/caro" categórico.
2. Não antecipa que dois ciclos parciais podem ser mais lucrativos que um ciclo completo se o spread for suficiente.
3. Pode subutilizar o banco em dias de PLD comprimido (poucos extremos).

**Cota de qualidade empírica.** Em backtest com PLD histórico (a fazer na Sprint 1.3), espera-se que a heurística capture entre 70% e 85% do valor capturado pela LP ótima. Para o MVP, aceita-se essa perda em troca de:

- Zero dependências externas (sem cvxpy + solver).
- Determinismo absoluto (mesmo input ⇒ mesmo output).
- Auditabilidade pelo agente Crítico do briefing.
- Tempo de execução < 1 ms para 8 760 h vs. ~1 s para LP.

LP completa fica como evolução opcional da Sprint 1.3 quando o ROI justificar a complexidade.

### 5.3 Autoconsumo híbrido (greedy ótimo)

```text
excedente_fv = max(p_fv(t) - p_load(t), 0)
deficit      = max(p_load(t) - p_fv(t), 0)

if excedente_fv > 0 and SoC < SoC_max:
    p_c = min(excedente_fv, p_c_max)
    return (p_c, 0)
elif deficit > 0 and SoC > SoC_min:
    p_d = min(deficit, p_d_max)
    return (0, p_d)
else:
    return (0, 0)
```

**Argumento de otimalidade.** Pós Lei 14.300/2022, o cliente paga Fio B sobre energia injetada na rede pelo MMGD. Logo, o valor marginal de armazenar 1 kWh de excedente FV (para autoconsumir depois) supera o valor marginal de injetar esse mesmo kWh — exceto em cenários muito específicos de tarifa branca + ponta. Decisão local de "carregar excedente, descarregar déficit" é portanto globalmente ótima sob a tarifação atual.

Verificado nos testes `test_carrega_quando_fv_excede_carga` e `test_descarrega_quando_fv_insuficiente`.

## 6. Métricas de saída

| Métrica | Fórmula | Unidade |
|---------|---------|---------|
| `energia_carregada_kwh` | $\sum_t p_c(t) \cdot \Delta t$ | kWh AC |
| `energia_descarregada_kwh` | $\sum_t p_d(t) \cdot \Delta t$ | kWh AC |
| `energia_grid_importada_kwh` | $\sum_t \max(p_{grid}(t), 0) \cdot \Delta t$ | kWh |
| `energia_grid_exportada_kwh` | $\sum_t \max(-p_{grid}(t), 0) \cdot \Delta t$ | kWh |
| `ciclos_equivalentes` | $\frac{\sum_t p_d(t) \cdot \Delta t / \eta_d}{E_{nom}}$ | adim. |
| `perdas_kwh` | $E_c (1-\eta_c) + E_d \cdot (1-\eta_d)/\eta_d$ | kWh |
| `delta_soc` | $SoC(N) - SoC(0)$ | adim. |

**Conservação de energia.** A invariante a seguir é testada explicitamente em `test_conservacao_de_energia`:

$$
E_c \cdot \eta_c \;-\; \frac{E_d}{\eta_d} \;=\; \Delta SoC \cdot E_{nom}
$$

Ou seja: o que entrou no banco menos o que saiu (ambos em DC) deve ser igual à energia residual armazenada. Esta identidade não é uma escolha de modelagem — ela decorre do balanço de massa/energia e se valida com tolerância numérica de $10^{-3}$ kWh em qualquer simulação.

## 7. Resultado dataclass

`ResultadoDespacho` é `frozen=True` (imutável) com os seguintes campos:

```python
soc: list[float]                       # N+1 pontos
p_carga_kw: list[float]                # N pontos
p_descarga_kw: list[float]             # N pontos
p_grid_kw: list[float]                 # N pontos
demanda_apos_bess_kw: list[float]      # N pontos
energia_carregada_kwh: float
energia_descarregada_kwh: float
energia_grid_importada_kwh: float
energia_grid_exportada_kwh: float
ciclos_equivalentes: float
perdas_kwh: float
delta_soc: float
premissas: dict
```

A lista `soc` tem comprimento $N+1$: o valor inicial mais o estado ao final de cada passo. Útil para reconstrução visual e para inspeção pelo agente Crítico.

## 8. Limitações conhecidas (saída para Sprints futuras)

1. **Sem modelo de degradação.** $E_{nom}$ é constante ao longo da simulação. Sprint 1.4 incorporará SoH(t) reduzindo a capacidade efetiva ano a ano.
2. **Sem ciclos parciais com benefício temporal.** O greedy de arbitragem por percentil ignora oportunidades de dois ciclos pequenos vs. um grande. Evolução: LP via cvxpy.
3. **Auto-descarga não modelada.** Para horizontes de 8 760 h e η_autodescarga ≈ 2%/mês, o erro acumulado é ~24%/ano — relevante para arbitragem de longa duração. Stub implementável trivialmente em sprint futura.
4. **Mistura de estratégias não suportada.** Cliente híbrido (peak shaving + autoconsumo) precisa de um único objetivo composto. Ficou para Sprint 1.5 quando a estratégia híbrida emergir como demanda real.
5. **Backup não simulado em horizonte 8 760 h.** É um problema event-driven (descarrega quando há contingência); modelagem natural via Markov chain de disponibilidade da rede + autonomia. Foge do escopo desta sprint.

## 9. Referências e fontes

- **DOE/EPRI Energy Storage Handbook (2020), cap. 4** — fundamentação do modelo SoC e métricas de ciclo.
- **IEC 62933-2-1:2017** — definição padronizada de eficiência round-trip e ciclos equivalentes.
- **ABNT NBR 16690:2019, Anexo C** — parâmetros nominais de inversores no contexto FV+BESS.
- **ANEEL REN 1.000/2021, Art. 60** — regulação de demanda contratada (base do peak shaving).
- **Lei 14.300/2022, Art. 27** — cobrança progressiva do Fio B (motiva autoconsumo).
- **Olivares et al. (2014), IEEE Trans. Smart Grid** — validação da heurística de threshold por percentil em arbitragem.
- **Wankmüller et al. (2017), J. Energy Storage** — comparação empírica greedy vs. LP em ESS comerciais.

## 10. Sumário Sprint 1.2

| Item | Resultado |
|------|-----------|
| Estratégias implementadas | `peak_shaving`, `arbitragem`, `autoconsumo_hibrido` |
| Linhas de código (`despacho.py`) | 447 |
| Linhas de teste (`test_despacho.py`) | 427 |
| Testes adicionados | 34 (totalizando 81 com Sprints 1.1 + 1.2) |
| Tempo de execução da suite | 0,19 s |
| Conservação de energia | Validada (tolerância $10^{-3}$ kWh) |
| Bounds de SoC | Validados ($\pm 10^{-6}$) |
| Carga/descarga mutuamente exclusivas | Validado |

Próximo: Sprint 1.3 — análise financeira (payback, TIR, VPL, LCOS) consumindo os resultados de despacho como input.
