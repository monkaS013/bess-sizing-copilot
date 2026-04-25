# Memorial de Cálculo — Modelo de Degradação SoH(t)

**Versão:** 1.0.0 — Sprint 1.4 (encerramento do núcleo determinístico)
**Módulo:** `bess_core.degradacao.calcular_soh_anual`
**Autor:** Vinicius Morais (HDT Energy)
**Última revisão:** 2026-04-24

---

## 1. Escopo

Este memorial fecha o núcleo determinístico do BESS Sizing Copilot com o modelo de degradação calendárica + cíclica do banco LFP/NMC/LTO ao longo da vida útil. É a peça que conecta a operação real (despacho horário) com a depreciação física do ativo, fornecendo a curva $SoH(t)$ que o agente Engenharia (Sprint 4) usará para advertir o cliente sobre o fim de vida útil.

## 2. Modelo matemático

A perda de capacidade ao longo do tempo é decomposta em duas componentes aditivas:

$$
SoH(t) = SoH(0) - k_{cal}^{eff}(T) \cdot t - k_{cyc}^{eff}(\mathrm{DoD}) \cdot N(t)
$$

Onde:

| Símbolo | Descrição | Unidade |
|---------|-----------|---------|
| $SoH(t)$ | State of Health (capacidade efetiva / nominal) | adim. |
| $k_{cal}^{eff}$ | Taxa calendárica efetiva ajustada por temperatura | 1/ano |
| $k_{cyc}^{eff}$ | Taxa cíclica efetiva ajustada por DoD | 1/ciclo |
| $t$ | Tempo decorrido | anos |
| $N(t)$ | Soma cumulativa de ciclos equivalentes até $t$ | ciclos |

Por convenção, $SoH(0) = 1$ e o resultado é clipado em zero para baixo (modelo linear não simula valores negativos, embora células reais possam apresentar runaway abaixo de 60% SoH).

### 2.1 Ajuste de Arrhenius para temperatura

A taxa calendárica $k_{cal}^{eff}$ depende exponencialmente da temperatura ambiente segundo a lei de Arrhenius:

$$
k_{cal}^{eff}(T) = k_{cal}^{ref} \cdot \exp\!\left[ \frac{E_a}{R} \left( \frac{1}{T_{ref}} - \frac{1}{T} \right) \right]
$$

Com $T$ em Kelvin, $T_{ref} = 298{,}15$ K (25 °C), $R = 8{,}314 \cdot 10^{-3}$ kJ/(mol·K), e $E_a$ a energia de ativação (60 kJ/mol para LFP).

**Regra prática:** a cada +10 °C, $k_{cal}^{eff}$ aproximadamente dobra. Verificada no teste `test_a_cada_10c_arrhenius_dobra` (razão 1,5 ≤ ratio ≤ 2,5).

### 2.2 Ajuste de DoD para fadiga cíclica

$$
k_{cyc}^{eff}(\mathrm{DoD}) = k_{cyc}^{ref} \cdot \left( \frac{\mathrm{DoD}}{\mathrm{DoD}_{ref}} \right)^{\beta}
$$

Com $\mathrm{DoD}_{ref} = 0{,}80$ e $\beta = 1{,}0$ por default (relação aproximadamente linear para LFP/NMC modernas; Schmalstieg 2014 reporta $\beta$ entre 0,8 e 1,5 dependendo da química).

## 3. Calibração contra fichas técnicas Tier 1

Os defaults adotados foram **calibrados** contra datasheets reais e divergem dos valores nominais do briefing (`0{,}025\%/\text{ciclo}$ é budget, não Tier 1).

| Química | $k_{cal}^{ref}$ (/ano) | $k_{cyc}^{ref}$ (/ciclo) | Justificativa |
|---------|------------------------|--------------------------|---------------|
| **LFP** | 0,012 | 3,33 × 10⁻⁵ | Huawei LUNA2000-S0: 6 000 ciclos a 80% SoH @ 80% DoD ⇒ 20%/6000 = 3,33 × 10⁻⁵ /ciclo |
| **NMC** | 0,020 | 6,00 × 10⁻⁵ | NMC comerciais: ~3 500 ciclos a 80% SoH (CATL, LG Chem) |
| **LTO** | 0,004 | 1,00 × 10⁻⁵ | LTO: 20 000 ciclos a 80% SoH (Toshiba SCiB) |

### 3.1 Por que divergir do briefing?

O briefing original especifica "0,025%/ciclo" como degradação cíclica. Esse valor, aplicado a 365 ciclos/ano, gera EoL de **1,8 anos** para LFP — incompatível com qualquer datasheet Tier 1 (Huawei, CATL, BYD, LG Chem). Possíveis interpretações do briefing:

1. **Erro de digitação:** "0,025%/ciclo" deveria ser "0,0025%/ciclo" (10× menos), o que aproxima de Tier 1.
2. **Linha budget:** células chinesas budget (não Tier 1) podem ter ~3 000 ciclos a 80% SoH, equivalentes a ~0,007%/ciclo — ainda 3× menor que o literal do briefing.
3. **Confusão entre EoL 70% e 80%:** se EoL for 70% SoH (não 80%), a taxa por ciclo dobra. Não é convenção padrão BR.

Adotei valores Tier 1 como default porque o BESS Sizing Copilot tem alinhamento HDT-Huawei. O usuário pode override via `k_cyc_ref_override` para simular linha budget.

## 4. Resultado dataclass

`ResultadoDegradacao` é `frozen=True` (imutável):

```python
soh_anual: list[float]                       # tamanho = horizonte+1
perda_calendarica_anual: list[float]         # tamanho = horizonte+1
perda_ciclica_anual: list[float]             # tamanho = horizonte+1
eol_anos: float | None                       # ano em que SoH cruza 80%
capacidade_efetiva_anual_kwh: list[float] | None  # se E_nom fornecida
k_cal_eff: float                             # taxa calendárica efetiva
k_cyc_eff: float                             # taxa cíclica efetiva
premissas: dict
```

A invariante $SoH(t) = 1 - perda\_cal(t) - perda\_cyc(t)$ (clipada em zero) é validada em `test_soma_perdas_eh_complemento_do_soh`.

## 5. Caso de validação

```python
calcular_soh_anual(
    quimica="LFP",
    dod_medio=0.80,
    ciclos_ano=365,
    temperatura_celsius=25.0,
    horizonte_anos=20,
)
```

| Ano | SoH | Perda calendárica | Perda cíclica |
|-----|-----|--------------------|----------------|
| 0 | 1,000 | 0,0% | 0,0% |
| 5 | 0,880 | 6,0% | 6,0% |
| 10 | 0,759 | 12,0% | 12,1% |
| 15 | 0,639 | 18,0% | 18,1% |
| 20 | 0,519 | 24,0% | 24,1% |

EoL @ 80% SoH: **8,32 anos** — coerente com janela 7-10 anos típica para LFP em uso intensivo (1 ciclo/dia, clima tropical).

### 5.1 Sensibilidade à temperatura (Arrhenius em ação)

| Temperatura | SoH ano 10 | EoL @ 80% |
|-------------|------------|-----------|
| 15 °C | 0,828 | 11,6 anos |
| 25 °C | 0,760 | 8,3 anos |
| 35 °C | 0,616 | 5,2 anos |
| 45 °C | 0,330 | 3,0 anos |

**Implicação operacional:** climatização do container BESS em região quente (Nordeste, Centro-Oeste) compensa investimento. A diferença entre 35 °C (sem AC) e 25 °C (com AC) é de ~3 anos de vida útil — facilmente paga o CAPEX adicional do sistema térmico.

### 5.2 Comparativo entre químicas

| Química | SoH ano 20 | EoL @ 80% | Aplicação típica |
|---------|------------|-----------|------------------|
| **LFP** | 0,519 | 8,3 anos | C&I peak shaving (Huawei LUNA2000) |
| **NMC** | 0,162 | 4,8 anos | EV (não recomendado p/ BESS estacionário) |
| **LTO** | 0,847 | > 20 anos | Backup hospitalar / dados críticos |

## 6. Integração com as outras sprints

A função `calcular_soh_anual` é desacoplada das anteriores — recebe parâmetros operacionais e devolve uma curva. O acoplamento natural é:

```
Sprint 1.2 (despacho) ──► ciclos_equivalentes/ano
Sprint 1.4 (degradação) ──► SoH(t) ──► capacidade_efetiva(t)
                                  └──► degradação_anual_economia (Sprint 1.3)
```

Por exemplo, para alimentar o modelo financeiro com degradação realista:

```python
deg = calcular_soh_anual('LFP', ciclos_ano=ciclos_do_despacho)
# Curva ano-a-ano da economia (proporcional a SoH):
economia_anual_t = [economia_inicial * deg.soh_anual[t] for t in range(20)]
```

Isso será abstraído pelo agente Engenharia (Sprint 4) — o usuário não precisa fazer essa composição manualmente.

## 7. Limitações reconhecidas

1. **Modelo linear até 80% SoH.** Após o knee point, células reais aceleram não-linearmente. Para horizontes > 15 anos com uso pesado, o modelo subestima a perda (otimista).
2. **Sem efeito de SoC médio.** Em LFP o efeito é menor; em NMC manter SoC em 100% acelera ~50% a degradação calendárica. Modelo só captura via override manual.
3. **Sem efeito de C-rate.** Descargas a 1C aceleram fadiga ~30% vs 0,5C. Default assume C-rate moderado.
4. **Sem dependência de calor por I²·R.** Operação a alta potência gera calor que se some à temperatura ambiente. Modelo trata $T$ como exógeno.
5. **Variabilidade entre células não modelada.** Bancos reais têm distribuição de Weibull no SoH inicial e na taxa de fadiga. O modelo determinístico assume célula média. Para análise de risco probabilístico, evoluir para Monte Carlo (Sprint financeira avançada).

## 8. Referências

- **Smith K., Saxon A., Keyser M., et al. (2017)** — *Life Prediction Model for Grid-Connected Li-Ion Battery Energy Storage System*. NREL Technical Report. Base do modelo aditivo cal+cyc adotado.
- **Schmalstieg J., Käbitz S., Ecker M., Sauer D.U. (2014)** — *A holistic aging model for Li(NiMnCo)O2 based 18650 lithium-ion batteries*. J. Power Sources 257. Calibração de $\beta_{DoD}$ e $E_a$.
- **Huawei LUNA2000 Performance Whitepaper (2023)** — datasheet para defaults LFP.
- **CATL EnerOne Cycle Life Test Report (2024)** — ciclos garantidos a 80% SoH.
- **Toshiba SCiB Industrial Battery Modules (2022)** — defaults LTO.

## 9. Sumário Sprint 1.4 + fechamento do núcleo

| Item | Resultado |
|------|-----------|
| Funções implementadas | `calcular_soh_anual` (degradação calendárica + cíclica + Arrhenius) |
| Linhas de código (`degradacao.py`) | 297 |
| Linhas de teste (`test_degradacao.py`) | 314 |
| Testes adicionados | 33 |
| **Total acumulado das 4 sprints** | **141 testes em 0,30 s** |
| Dependências externas | **Zero** (só `math` e `dataclasses`) |
| Memoriais técnicos escritos | 5 (dimensionamento, casos validação, despacho, financeiro, degradação) |

## 10. Estado consolidado do `bess-core` v1.0.0

```text
bess-core v1.0.0
├── dimensionamento.py    [Sprint 1.1] sizing 3 estratégias  ✓
├── despacho.py           [Sprint 1.2] dispatch 8760h        ✓
├── financeiro.py         [Sprint 1.3] payback/TIR/VPL/LCOS  ✓
└── degradacao.py         [Sprint 1.4] SoH(t) + Arrhenius    ✓
```

**Núcleo determinístico fechado.** Próximas sprints saem do território "matemática auditável" e entram em "agente + interface":

- **Sprint 2** — Single agent (Claude Sonnet) usando estas 6 funções como tools, interface Streamlit.
- **Sprint 3** — Frontend Next.js + Supabase + deploy Vercel/Railway.
- **Sprint 4** — Multi-agente (Discovery + Engenharia + Crítico + Proposta).

A partir daqui, **toda decisão técnica crítica está calculada determinística e auditavelmente** — o LLM só orquestra, nunca calcula. É a defesa central do projeto contra a crítica óbvia de "IA é caixa-preta": o cálculo elétrico/financeiro nunca passa pelo modelo de linguagem.
