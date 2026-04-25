# Memorial de Cálculo — Análise Financeira

**Versão:** 0.4.0 — Sprint 1.3
**Módulo:** `bess_core.financeiro.analisar_financeiro`
**Autor:** Vinicius Morais (HDT Energy)
**Última revisão:** 2026-04-24

---

## 1. Escopo

Este memorial descreve o modelo financeiro adotado para avaliação de viabilidade de projetos BESS. Consome como input os resultados da Sprint 1.1 (CAPEX dimensionado) e Sprint 1.2 (energia descarregada anual + economia projetada) e produz cinco indicadores consolidados: payback simples, payback descontado, TIR, VPL e LCOS.

A abordagem é **determinística** — Monte Carlo (P50/P90) fica explicitamente para evolução posterior, conforme diretriz §8 do briefing ("só depois que payback simples funcionar"). A análise de sensibilidade ±20% em quatro variáveis principais cumpre o papel de capturar incerteza no MVP.

## 2. Modelo de fluxo de caixa

### 2.1 Estrutura básica

| Período | Fluxo nominal |
|---------|---------------|
| Ano 0 | $-CAPEX$ |
| Ano $t$ (1 ≤ $t$ ≤ $N$) | $CF_t = economia_t - OPEX_t$ |
| Ano $N$ | $+ VR$ (valor residual, se aplicável) |

Onde:

$$
\begin{aligned}
economia_t &= economia_{anual} \cdot (1 - \delta)^{t-1} \\
OPEX_t     &= OPEX_{anual}      \cdot (1 + i)^{t-1}
\end{aligned}
$$

### 2.2 Premissas conservadoras (defaults)

| Variável | Símbolo | Default | Justificativa |
|----------|---------|---------|---------------|
| Horizonte | $N$ | 20 anos | Vida útil garantida típica para LFP (Huawei LUNA2000-S0/S1) |
| WACC | $r$ | 12 %/ano | Taxa-alvo padrão de infraestrutura de energia no Brasil |
| Degradação anual | $\delta$ | 2 %/ano | Datasheet LFP Tier 1 (CATL EnerOne, Huawei LUNA2000) |
| Inflação OPEX | $i$ | 4 %/ano | Meta BCB de longo prazo |
| Valor residual | $VR$ | 0 | Sem mercado secundário maduro para BESS no BR |

A degradação $\delta$ aplica-se **à economia**, não à capacidade nominal — é a interface entre o modelo financeiro e o despacho. Se o banco perde 2% de capacidade efetiva por ano, a energia descarregada cai aproximadamente 2%/ano e a economia tarifária acompanha.

## 3. Indicadores

### 3.1 Valor Presente Líquido (VPL)

$$
VPL = -CAPEX + \sum_{t=1}^{N} \frac{CF_t}{(1+r)^t} + \frac{VR}{(1+r)^N}
$$

Implementação em `_vpl(fluxos, taxa)` — soma direta sem otimizações vetorizadas (suficiente para horizontes ≤ 50 anos; performance não é gargalo).

### 3.2 Taxa Interna de Retorno (TIR)

Definida como a raiz de $VPL(r) = 0$. Resolvida numericamente em `_tir_bisseccao` via **bissecção** no intervalo $[-99\%,\ 1000\%]$ com tolerância $10^{-7}$.

**Por que bissecção?** Newton-Raphson converge mais rápido mas exige derivada e pode falhar em projetos com múltiplas mudanças de sinal nos fluxos. Bissecção é mais lenta porém **garantidamente convergente** quando o sinal muda no intervalo. Para o uso atual (≤ 200 iterações, ~1 ms), a perda de performance é irrelevante.

Retorna `None` se não há cruzamento de zero no intervalo de busca — caso de projeto inviável onde nenhuma taxa zera o VPL.

### 3.3 Payback simples e descontado

```python
def _payback_anos(acumulado, fluxos, capex):
    for t in 1..N:
        if acumulado[t] >= 0:
            falta = -acumulado[t-1]
            return (t-1) + falta / fluxos[t]   # interpolação linear
    return None
```

A interpolação linear entre o ano em que o acumulado vira positivo e o anterior dá uma resolução fracionária do payback (ex: 4,67 anos), útil em comparações entre projetos.

Retorna `None` se o projeto não se paga no horizonte simulado.

**Identidade verificada nos testes:** sem degradação e sem inflação OPEX, o payback simples é exatamente $CAPEX / (economia - OPEX)$. Teste `test_payback_simples_sem_degradacao_eh_capex_dividido_cf`.

### 3.4 LCOS — Levelized Cost of Storage

Convenção IEA / NREL:

$$
LCOS = \frac{CAPEX + \displaystyle\sum_{t=1}^{N} \frac{OPEX_t}{(1+r)^t} - \frac{VR}{(1+r)^N}}{\displaystyle\sum_{t=1}^{N} \frac{E_t}{(1+r)^t}}
$$

Onde $E_t$ é a energia descarregada no ano $t$ (com degradação aplicada). Resultado em R$/kWh; multiplicado por 1000 → R$/MWh.

**Interpretação:** LCOS responde à pergunta "qual é o custo unitário de cada kWh entregue pelo banco ao longo da vida útil?". É o equivalente em armazenamento ao LCOE (Levelized Cost of Energy) usado em geração.

**Quando usar:** LCOS faz mais sentido para projetos de **arbitragem** (onde a métrica natural é R$/MWh entregue). Para **peak shaving** o LCOS tende a ser alto (a métrica relevante é R$/kW evitado, não R$/kWh entregue) — usar payback e TIR é mais defensável.

## 4. Análise de sensibilidade ±20%

Quatro variáveis varridas com $\pm 20\%$:

| Variável | Direção esperada |
|----------|------------------|
| CAPEX | $\uparrow$ CAPEX $\Rightarrow$ $\downarrow$ VPL |
| OPEX | $\uparrow$ OPEX $\Rightarrow$ $\downarrow$ VPL |
| Economia | $\uparrow$ Economia $\Rightarrow$ $\uparrow$ VPL |
| WACC | $\uparrow$ WACC $\Rightarrow$ $\downarrow$ VPL |

A saída `sensibilidade` é uma lista de `SensibilidadeItem` com 4 entradas. Cada item contém valor central, variantes ±20% e o VPL correspondente — pronto para alimentar um **tornado chart** no agente Proposta (Sprint 4).

**Hipótese empírica testada:** em projetos BESS BR a economia tipicamente domina o tornado (maior amplitude). Verificado em `test_economia_eh_variavel_mais_sensivel`.

## 5. Conexão com as outras sprints

```text
Sprint 1.1 (sizing) ─────────────► CAPEX_estimado
                                       │
Sprint 1.2 (despacho) ──┬─► economia_anual (kWh×tarifa)
                        └─► energia_descarregada_anual
                                       │
                                       ▼
Sprint 1.3 (financeiro) ────────► payback, TIR, VPL, LCOS
```

A função `analisar_financeiro` é desacoplada das anteriores — recebe escalares, não acopla a `ResultadoDespacho`. Decisão deliberada para que o agente Engenharia (Sprint 4) possa montar fluxos de caixa de cenários comparativos sem reexecutar dispatchs.

## 6. Caso de validação

```python
analisar_financeiro(
    capex_brl=1_500_000,
    opex_anual_brl=15_000,
    economia_anual_brl=350_000,
    energia_descarregada_anual_kwh=110_000,
)
```

| Indicador | Valor | Interpretação |
|-----------|-------|---------------|
| Payback simples | 4,67 anos | Retorno nominal do investimento |
| Payback descontado | 7,50 anos | Retorno real considerando custo de capital |
| TIR | 19,60 %/a.a. | > WACC 12% → projeto cria valor |
| VPL @ 12% | R$ +682.068 | Geração líquida de valor |
| LCOS | R$ 2.249/MWh | Alto (típico em peak shaving) |

Tornado da sensibilidade (R$ de range no VPL):

| Variável | Range VPL |
|----------|-----------|
| Economia | R$ 930.792 |
| WACC | R$ 606.471 |
| CAPEX | R$ 600.000 |
| OPEX | R$ 57.964 |

Ordem coerente: **economia domina**, OPEX é o menos sensível (porque OPEX é pequeno relativo à economia neste exemplo).

## 7. Limitações reconhecidas

1. **Sem benefício fiscal de depreciação.** Para empresas no Lucro Real, BESS é depreciável em ~10 anos e gera escudo fiscal de IR/CSLL. Não modelado no MVP — varia por regime tributário e adiciona complexidade. Documentar quando virar ferramenta comercial (post-Sprint 4).
2. **CAPEX em BRL fixo.** BESS é predominantemente importado, exposto a câmbio. Tratado como custo single-shot em moeda local — simplificação aceitável para MVP.
3. **Sem custos de troca de componentes.** PCS/inversor tem MTBF tipicamente menor que vida útil do banco LFP. Em projetos > 15 anos, contemplar substituição do PCS no ano 12-15.
4. **Sem modelo de risco regulatório.** Lei 14.300 estabelece progressão do Fio B até 2028. Mudanças regulatórias após esse horizonte não são modeladas — risco assumido como exógeno.
5. **TIR única vs múltiplas raízes.** Para fluxos com múltiplas mudanças de sinal (ex.: troca de banco no meio do horizonte) podem existir múltiplas TIRs. Bissecção retorna a primeira encontrada — em projetos BESS típicos não acontece, mas é limitação técnica.

## 8. Referências

- **Brealey, Myers, Allen — Principles of Corporate Finance**, 13ª ed. — fundamentação de VPL, TIR e payback descontado.
- **NREL Cost Projections for Utility-Scale Battery Storage (2023)** — convenções de LCOS e premissas de degradação.
- **IEA Innovation Outlook: Smart Charging for Electric Vehicles (2018)** — definição padrão de LCOS adotada.
- **Lazard's Levelized Cost of Storage Analysis v8.0 (2022)** — benchmarks setoriais.
- **Lei 14.300/2022** — base regulatória do BR.
- **Manual ANEEL de Tarifa Branca (2022)** — base do cálculo de economia em peak shaving.

## 9. Sumário Sprint 1.3

| Item | Resultado |
|------|-----------|
| Indicadores implementados | Payback (S/D), TIR, VPL, LCOS, Sensibilidade ±20% |
| Linhas de código (`financeiro.py`) | 436 |
| Linhas de teste (`test_financeiro.py`) | 339 |
| Testes adicionados | 27 (totalizando 108 com Sprints 1.1 → 1.3) |
| Tempo de execução da suite | 0,25 s |
| Identidades matemáticas testadas | VPL@TIR=0; VPL@wacc=0=Σnominal; payback=CAPEX/(eco-opex) |
| Dependências externas adicionadas | **Zero** (matemática pura) |

Próximo: Sprint 1.4 — modelo de degradação SoH(t) calendárico + cíclico, fechando o núcleo determinístico antes do agente Sprint 2.
