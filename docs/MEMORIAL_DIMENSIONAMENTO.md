# Memorial de Cálculo — Dimensionamento BESS para Peak Shaving

**Versão:** 0.1.0 — Sprint 1.1
**Módulo:** `bess_core.dimensionamento.dimensionar_peak_shaving`
**Autor:** Vinicius Morais (HDT Energy)
**Última revisão:** 2026-04-24

---

## 1. Escopo

Este memorial descreve a metodologia de cálculo adotada para o dimensionamento de Sistemas de Armazenamento de Energia (BESS) operando em regime de **peak shaving** — corte da demanda contratada — para consumidores do Grupo A (média e alta tensão), conforme classificação da REN ANEEL nº 1.000/2021.

A função objeto deste memorial recebe um perfil horário de carga e parâmetros operacionais e devolve a capacidade nominal (kWh), potência nominal (kW) e C-rate do banco necessário para manter a demanda do medidor abaixo de um patamar de referência (tipicamente a demanda contratada).

## 2. Modelo Matemático

### 2.1 Excedente instantâneo

Para cada instante $t$ amostrado em passos uniformes de $\Delta t$ horas:

$$
P_{exc}(t) = \max\bigl(P_{carga}(t) - P_{contratada},\, 0\bigr)
$$

onde $P_{carga}(t)$ é a demanda da carga e $P_{contratada}$ é o limiar de corte (kW).

### 2.2 Identificação de eventos de pico

Um **evento de pico** é definido como uma sequência contígua de amostras com $P_{exc}(t) > 0$. Para cada evento $k$:

$$
E_{evento,k} = \sum_{t \in k} P_{exc}(t) \cdot \Delta t \quad [\text{kWh}]
$$

### 2.3 Sizing — energia e potência

A **potência mínima** do conversor corresponde ao maior excedente instantâneo:

$$
P_{shave} = \max_t P_{exc}(t)
$$

A **energia útil** que o banco precisa entregar corresponde ao pior evento (assume-se que há tempo de recarga off-peak entre eventos):

$$
E_{util} = \max_k E_{evento,k}
$$

### 2.4 Derating

Aplica-se DoD, perdas de descarga e reserva técnica para chegar à energia e potência nominais (de placa).

Adotando eficiência simétrica de carga e descarga:

$$
\eta_d = \eta_c = \sqrt{\eta_{rt}}
$$

Energia nominal:

$$
E_{nominal} = \frac{E_{util}}{\mathrm{DoD} \cdot \eta_d} \cdot \bigl(1 + r_{tec}\bigr)
$$

Potência nominal:

$$
P_{nominal} = \frac{P_{shave}}{\eta_d} \cdot \bigl(1 + r_{tec}\bigr)
$$

C-rate:

$$
C_{rate} = \frac{P_{nominal}}{E_{nominal}} \quad [\text{h}^{-1}]
$$

## 3. Premissas

| Símbolo | Default | Justificativa |
|---------|---------|---------------|
| $\mathrm{DoD}$ | 0.90 | LFP comerciais (Huawei LUNA2000-S0/S1, CATL EnerOne) operam tipicamente entre 5% e 95% SoC. |
| $\eta_{rt}$ | 0.92 | Eficiência round-trip declarada por fabricantes Tier 1 para LFP + inversor central. |
| $r_{tec}$ | 0.10 | Reserva técnica de 10% — boa prática EPRI para absorver incerteza de medição e degradação inicial. |
| $\Delta t$ | 1.0 h | Granularidade típica de medição faturamento-grade (Grupo A — REN 1.000 Art. 65). |

A hipótese de eficiência simétrica ($\eta_d = \eta_c = \sqrt{\eta_{rt}}$) é uma simplificação consagrada na literatura quando o fabricante reporta apenas $\eta_{rt}$. Ela é exata se as perdas em carga e descarga forem do mesmo tipo (resistência interna constante).

A reserva técnica é aplicada **multiplicativamente** sobre energia *e* potência. Como ambas crescem pelo mesmo fator, o C-rate permanece invariante — propriedade verificada no teste `test_efeito_da_reserva_tecnica`.

## 4. Caso de Validação — Indústria 500 kW

### 4.1 Cenário

| Item | Valor |
|------|-------|
| Demanda contratada | 500 kW |
| Demanda de pico | 650 kW |
| Duração do pico | 2 h/dia (14 h às 16 h) |
| Frequência | 5 dias úteis × 52 semanas = 260 eventos/ano |
| Tarifa de demanda (referência) | R\$ 23,50/kW |
| DoD, $\eta_{rt}$, $r_{tec}$ | 0,90; 0,92; 0,10 |

### 4.2 Cálculo manual

$$
\begin{aligned}
P_{shave}    &= 650 - 500                                 = 150{,}00\;\text{kW} \\
E_{util}     &= 150 \times 2                              = 300{,}00\;\text{kWh} \\
\eta_d       &= \sqrt{0{,}92}                             \approx 0{,}9592 \\
E_{nominal}  &= \frac{300}{0{,}9 \times 0{,}9592} \times 1{,}10  \approx 382{,}18\;\text{kWh} \\
P_{nominal}  &= \frac{150}{0{,}9592} \times 1{,}10               \approx 172{,}04\;\text{kW} \\
C_{rate}     &= \frac{172{,}04}{382{,}18}                        \approx 0{,}450\;\text{h}^{-1}
\end{aligned}
$$

### 4.3 Resultado da função

| Grandeza | Manual | Função | Δ |
|----------|--------|--------|---|
| $P_{shave}$ | 150,00 kW | 150,00 kW | 0,00 % |
| $E_{evento,max}$ | 300,00 kWh | 300,00 kWh | 0,00 % |
| $E_{nominal}$ | 382,18 kWh | 382,28 kWh | +0,03 % |
| $P_{nominal}$ | 172,04 kW | 172,02 kW | −0,01 % |
| $C_{rate}$ | 0,450 | 0,450 | 0,00 % |
| Eventos | 5 | 5 | — |

Diferenças dentro da tolerância adotada de 2% (compatível com incerteza de fichas técnicas de fabricantes).

## 5. Limitações conhecidas (a tratar em sprints futuras)

1. **Recarga entre eventos não é modelada.** Sprint 1.1 assume que sempre há tempo off-peak suficiente para recarga completa. Sprint 1.2 (despacho 8760h) tratará o caso de eventos consecutivos sem recarga adequada.
2. **Degradação não é considerada.** A capacidade nominal calculada vale para o ano 1. Sprint 1.4 incorporará SoH(t) e fará oversize compensatório.
3. **Tarifa de demanda não influencia o sizing.** Está apenas registrada nas premissas para auditoria. Otimização tarifária (escolher patamar ótimo de corte) será função separada na Sprint 1.3.
4. **Perfil determinístico.** Variabilidade da carga não é modelada. Monte Carlo virá com a Sprint 1.3.

## 6. Referências normativas

- **ABNT NBR 5410:2004** — Instalações elétricas de baixa tensão.
- **ABNT NBR 16690:2019** — Instalações elétricas de arranjos fotovoltaicos — Requisitos de projeto.
- **IEC 62933-2-1:2017** — Electrical energy storage systems — Part 2-1: Unit parameters and testing methods.
- **ANEEL REN nº 1.000/2021** — Estabelece as Regras de Prestação do Serviço Público de Distribuição de Energia Elétrica.
- **Lei nº 14.300/2022** — Marco legal da micro e minigeração distribuída.
- **DOE/EPRI Energy Storage Handbook (2020)** — Convenções de DoD, $\eta_{rt}$ e derating.
- **Huawei LUNA2000 S0/S1 Datasheet (rev 2024)** — Parâmetros de banco LFP comercial.
