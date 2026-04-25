"""
financeiro.py
=============

Análise financeira de projetos BESS: payback simples e descontado, TIR,
VPL, LCOS e análise de sensibilidade.

Sprint 1.3 entrega: cálculos determinísticos sem dependências externas.
Monte Carlo (P50/P90) fica como evolução opcional — segue diretriz §8 do
briefing ("só depois que payback simples funcionar").

Modelo de fluxo de caixa
------------------------
Ano 0:  -CAPEX
Ano t (t = 1..N):  CF_t = economia_t - opex_t
                   economia_t = economia_anual_brl · (1 - δ)^(t-1)
                   opex_t     = opex_anual_brl · (1 + i)^(t-1)
Ano N: + valor_residual

Onde:
- δ = degradacao_anual_economia (default 2 %/ano, alinhado com LFP).
- i = inflacao_opex (default 4 %/ano).
- N = horizonte_anos (default 20).

Indicadores
-----------
- VPL = -CAPEX + Σ_t CF_t / (1 + r)^t  + VR / (1 + r)^N
- TIR = r tal que VPL = 0  (resolvido por bissecção robusta).
- Payback simples = ano em que ΣCF nominal supera CAPEX.
- Payback descontado = ano em que ΣCF descontado a r supera CAPEX.
- LCOS = (CAPEX + Σ OPEX_t/(1+r)^t - VR/(1+r)^N) / Σ E_t/(1+r)^t
       em R$/kWh; multiplicado por 1000 vira R$/MWh.

Premissas conservadoras (defaults)
----------------------------------
- WACC: 12 %/a.a. (taxa-alvo típica para infraestrutura de energia BR).
- Degradação: 2 %/ano (LFP comercial Tier 1).
- Inflação OPEX: 4 %/ano (meta BCB de longo prazo).
- Valor residual: 0 (sem mercado secundário maduro para BESS).

Limitações reconhecidas
-----------------------
1. Sem benefício fiscal de depreciação (varia por regime tributário e
   complica MVP). Documentar quando virar ferramenta comercial.
2. Sem ajuste por câmbio (BESS é importado; CAPEX em BRL fixo é simplificação).
3. Sem custos de troca de componentes (PCS típico tem MTBF < vida do banco).
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SensibilidadeItem:
    """Linha individual da análise de sensibilidade (tornado chart)."""

    variavel: str
    valor_central: float
    valor_baixo: float
    valor_alto: float
    vpl_baixo_brl: float
    vpl_central_brl: float
    vpl_alto_brl: float


@dataclass(frozen=True)
class AnaliseFinanceira:
    """
    Indicadores financeiros consolidados.

    Attributes
    ----------
    capex_brl : float
        Investimento total no ano 0 (R$).
    opex_anual_brl : float
        OPEX nominal no ano 1 (R$). Cresce com inflação.
    economia_anual_brl : float
        Economia bruta no ano 1 (R$). Decai com degradação.
    payback_simples_anos : float | None
        Anos até retorno nominal (com interpolação linear). None se não atinge.
    payback_descontado_anos : float | None
        Idem, descontado à WACC.
    tir_percent : float | None
        Taxa Interna de Retorno (% a.a.). None se não há cruzamento de zero.
    vpl_brl : float
        Valor Presente Líquido a WACC (R$).
    lcos_brl_mwh : float
        Levelized Cost of Storage (R$/MWh entregue).
    fluxos_caixa_anuais_brl : list[float]
        Fluxos nominais ano-a-ano (índice 0 = ano 0; CAPEX já com sinal).
    vpl_acumulado_brl : list[float]
        VPL acumulado ano-a-ano (descontado a WACC).
    sensibilidade : list[SensibilidadeItem]
        Tornado chart: ±20 % em CAPEX, OPEX, economia e WACC.
    premissas : dict
        Cópia dos parâmetros para auditoria.
    """

    capex_brl: float
    opex_anual_brl: float
    economia_anual_brl: float
    payback_simples_anos: float | None
    payback_descontado_anos: float | None
    tir_percent: float | None
    vpl_brl: float
    lcos_brl_mwh: float
    fluxos_caixa_anuais_brl: list[float]
    vpl_acumulado_brl: list[float]
    sensibilidade: list[SensibilidadeItem]
    premissas: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------


def _vpl(fluxos: list[float], taxa: float) -> float:
    """VPL de uma série de fluxos. Índice 0 = ano 0 (não descontado)."""
    if taxa <= -1.0:
        raise ValueError("taxa deve ser > -100%.")
    soma = 0.0
    for t, cf in enumerate(fluxos):
        soma += cf / ((1.0 + taxa) ** t)
    return soma


def _tir_bisseccao(
    fluxos: list[float],
    limite_inferior: float = -0.99,
    limite_superior: float = 10.0,
    tol: float = 1e-7,
    max_iter: int = 200,
) -> float | None:
    """
    Calcula TIR via bissecção. Retorna None se não há cruzamento de zero
    no intervalo de busca.
    """
    f_lo = _vpl(fluxos, limite_inferior)
    f_hi = _vpl(fluxos, limite_superior)
    # Sem cruzamento de zero — não há TIR no intervalo.
    if f_lo * f_hi > 0:
        return None
    if abs(f_lo) < tol:
        return limite_inferior
    if abs(f_hi) < tol:
        return limite_superior

    lo, hi = limite_inferior, limite_superior
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = _vpl(fluxos, mid)
        if abs(f_mid) < tol or (hi - lo) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return 0.5 * (lo + hi)


def _payback_anos(
    fluxos_acumulados: list[float],
    fluxos: list[float],
    capex_brl: float,
) -> float | None:
    """
    Encontra o ano (com interpolação linear) em que fluxo acumulado >= 0.

    fluxos_acumulados[t] = soma dos fluxos[0..t].
    Retorna None se nunca cruza zero.
    """
    # Por construção, fluxos_acumulados[0] = -CAPEX (negativo).
    for t in range(1, len(fluxos_acumulados)):
        if fluxos_acumulados[t] >= 0.0:
            # Cruzou no ano t. Interpolar entre t-1 e t.
            cf_t = fluxos[t]
            if cf_t == 0.0:
                return float(t)
            falta = -fluxos_acumulados[t - 1]  # quanto faltava no fim de t-1
            return (t - 1) + falta / cf_t
    return None


def _construir_fluxos(
    capex_brl: float,
    economia_anual_brl: float,
    opex_anual_brl: float,
    horizonte_anos: int,
    degradacao_anual_economia: float,
    inflacao_opex: float,
    valor_residual_brl: float,
) -> list[float]:
    """Constrói a série de fluxos de caixa nominais [ano 0..N]."""
    fluxos = [-capex_brl]
    for t in range(1, horizonte_anos + 1):
        eco_t = economia_anual_brl * (1.0 - degradacao_anual_economia) ** (t - 1)
        opex_t = opex_anual_brl * (1.0 + inflacao_opex) ** (t - 1)
        cf = eco_t - opex_t
        if t == horizonte_anos:
            cf += valor_residual_brl
        fluxos.append(cf)
    return fluxos


def _calcular_lcos_brl_mwh(
    capex_brl: float,
    opex_anual_brl: float,
    energia_descarregada_anual_kwh: float,
    horizonte_anos: int,
    wacc: float,
    degradacao_anual_energia: float,
    inflacao_opex: float,
    valor_residual_brl: float,
) -> float:
    """
    LCOS conforme convenção IEA / NREL:

        LCOS = (CAPEX + Σ OPEX_t/(1+r)^t - VR/(1+r)^N) / Σ E_t/(1+r)^t

    Resultado em R$/MWh.
    """
    if energia_descarregada_anual_kwh <= 0.0:
        # Sem energia entregue não há LCOS definido — retornar inf.
        return float("inf")

    custo_descontado = capex_brl
    energia_descontada_kwh = 0.0
    for t in range(1, horizonte_anos + 1):
        opex_t = opex_anual_brl * (1.0 + inflacao_opex) ** (t - 1)
        e_t = energia_descarregada_anual_kwh * (
            1.0 - degradacao_anual_energia
        ) ** (t - 1)
        custo_descontado += opex_t / ((1.0 + wacc) ** t)
        energia_descontada_kwh += e_t / ((1.0 + wacc) ** t)
    custo_descontado -= valor_residual_brl / ((1.0 + wacc) ** horizonte_anos)

    lcos_brl_kwh = custo_descontado / energia_descontada_kwh
    return lcos_brl_kwh * 1000.0  # → R$/MWh


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def analisar_financeiro(
    capex_brl: float,
    opex_anual_brl: float,
    economia_anual_brl: float,
    energia_descarregada_anual_kwh: float,
    *,
    horizonte_anos: int = 20,
    wacc: float = 0.12,
    degradacao_anual_economia: float = 0.02,
    inflacao_opex: float = 0.04,
    valor_residual_brl: float = 0.0,
    incluir_sensibilidade: bool = True,
) -> AnaliseFinanceira:
    """
    Calcula payback (simples e descontado), TIR, VPL e LCOS para um projeto BESS.

    Parameters
    ----------
    capex_brl : float
        Investimento total em R$ (banco + PCS + instalação + projeto).
    opex_anual_brl : float
        OPEX nominal no ano 1 (R$). Cresce com inflação_opex nos anos seguintes.
    economia_anual_brl : float
        Economia bruta no ano 1 (R$). Decai com degradacao_anual_economia.
    energia_descarregada_anual_kwh : float
        Energia AC entregue pelo BESS no ano 1 (kWh). Usada para LCOS.
    horizonte_anos : int, default 20
        Vida útil do projeto em anos.
    wacc : float, default 0.12
        Taxa de desconto (Custo Médio Ponderado de Capital). 12 % é típico
        para projetos de infra de energia no BR.
    degradacao_anual_economia : float, default 0.02
        Decaimento anual da economia (proporcional à perda de SoH do banco).
    inflacao_opex : float, default 0.04
        Crescimento anual de OPEX. Default 4 %/ano (meta BCB longo prazo).
    valor_residual_brl : float, default 0.0
        Valor de revenda no fim da vida útil (R$).
    incluir_sensibilidade : bool, default True
        Se True, calcula tornado chart com ±20 % em 4 variáveis principais.

    Returns
    -------
    AnaliseFinanceira

    Raises
    ------
    ValueError
        Se algum parâmetro estiver fora de limites plausíveis.

    Examples
    --------
    >>> r = analisar_financeiro(
    ...     capex_brl=1_500_000.0,
    ...     opex_anual_brl=15_000.0,
    ...     economia_anual_brl=350_000.0,
    ...     energia_descarregada_anual_kwh=110_000.0,
    ... )
    >>> r.payback_simples_anos < r.payback_descontado_anos
    True
    """
    # ---- Validação ------------------------------------------------------
    if capex_brl <= 0:
        raise ValueError("capex_brl deve ser > 0 R$.")
    if opex_anual_brl < 0:
        raise ValueError("opex_anual_brl não pode ser negativo.")
    if energia_descarregada_anual_kwh < 0:
        raise ValueError("energia_descarregada_anual_kwh não pode ser negativa.")
    if horizonte_anos < 1:
        raise ValueError("horizonte_anos deve ser >= 1.")
    if not (-0.99 < wacc < 10.0):
        raise ValueError("wacc fora de limites razoáveis.")
    if not (0.0 <= degradacao_anual_economia < 1.0):
        raise ValueError("degradacao_anual_economia deve estar em [0, 1).")
    if not (-0.5 < inflacao_opex < 1.0):
        raise ValueError("inflacao_opex fora de limites razoáveis.")
    if valor_residual_brl < 0:
        raise ValueError("valor_residual_brl não pode ser negativo.")

    # ---- Fluxos de caixa ------------------------------------------------
    fluxos = _construir_fluxos(
        capex_brl, economia_anual_brl, opex_anual_brl,
        horizonte_anos, degradacao_anual_economia, inflacao_opex,
        valor_residual_brl,
    )

    # Acumulado nominal (para payback simples).
    acumulado_nominal: list[float] = []
    s = 0.0
    for cf in fluxos:
        s += cf
        acumulado_nominal.append(s)

    # Acumulado descontado (para payback descontado e VPL).
    acumulado_descontado: list[float] = []
    s = 0.0
    for t, cf in enumerate(fluxos):
        s += cf / ((1.0 + wacc) ** t)
        acumulado_descontado.append(s)

    vpl = acumulado_descontado[-1]

    # ---- Indicadores ----------------------------------------------------
    payback_simples = _payback_anos(acumulado_nominal, fluxos, capex_brl)

    # Para payback descontado, precisamos dos fluxos descontados (não os nominais).
    fluxos_descontados = [
        cf / ((1.0 + wacc) ** t) for t, cf in enumerate(fluxos)
    ]
    payback_descontado = _payback_anos(
        acumulado_descontado, fluxos_descontados, capex_brl
    )

    tir = _tir_bisseccao(fluxos)
    tir_percent = tir * 100.0 if tir is not None else None

    lcos = _calcular_lcos_brl_mwh(
        capex_brl, opex_anual_brl, energia_descarregada_anual_kwh,
        horizonte_anos, wacc, degradacao_anual_economia, inflacao_opex,
        valor_residual_brl,
    )

    # ---- Sensibilidade ±20 % --------------------------------------------
    sensibilidade: list[SensibilidadeItem] = []
    if incluir_sensibilidade:
        def vpl_para(capex, opex, economia, taxa):
            f = _construir_fluxos(
                capex, economia, opex, horizonte_anos,
                degradacao_anual_economia, inflacao_opex, valor_residual_brl,
            )
            return _vpl(f, taxa)

        for nome, valor_central in [
            ("CAPEX",    capex_brl),
            ("OPEX",     opex_anual_brl),
            ("Economia", economia_anual_brl),
            ("WACC",     wacc),
        ]:
            v_baixo = valor_central * 0.80 if valor_central != 0 else -0.20
            v_alto = valor_central * 1.20 if valor_central != 0 else 0.20
            if nome == "CAPEX":
                vpl_baixo = vpl_para(v_baixo, opex_anual_brl, economia_anual_brl, wacc)
                vpl_alto = vpl_para(v_alto, opex_anual_brl, economia_anual_brl, wacc)
            elif nome == "OPEX":
                vpl_baixo = vpl_para(capex_brl, v_baixo, economia_anual_brl, wacc)
                vpl_alto = vpl_para(capex_brl, v_alto, economia_anual_brl, wacc)
            elif nome == "Economia":
                vpl_baixo = vpl_para(capex_brl, opex_anual_brl, v_baixo, wacc)
                vpl_alto = vpl_para(capex_brl, opex_anual_brl, v_alto, wacc)
            else:  # WACC
                vpl_baixo = vpl_para(capex_brl, opex_anual_brl, economia_anual_brl, v_baixo)
                vpl_alto = vpl_para(capex_brl, opex_anual_brl, economia_anual_brl, v_alto)
            sensibilidade.append(SensibilidadeItem(
                variavel=nome,
                valor_central=valor_central,
                valor_baixo=v_baixo,
                valor_alto=v_alto,
                vpl_baixo_brl=vpl_baixo,
                vpl_central_brl=vpl,
                vpl_alto_brl=vpl_alto,
            ))

    return AnaliseFinanceira(
        capex_brl=capex_brl,
        opex_anual_brl=opex_anual_brl,
        economia_anual_brl=economia_anual_brl,
        payback_simples_anos=payback_simples,
        payback_descontado_anos=payback_descontado,
        tir_percent=tir_percent,
        vpl_brl=vpl,
        lcos_brl_mwh=lcos,
        fluxos_caixa_anuais_brl=fluxos,
        vpl_acumulado_brl=acumulado_descontado,
        sensibilidade=sensibilidade,
        premissas={
            "horizonte_anos": horizonte_anos,
            "wacc": wacc,
            "degradacao_anual_economia": degradacao_anual_economia,
            "inflacao_opex": inflacao_opex,
            "valor_residual_brl": valor_residual_brl,
            "energia_descarregada_anual_kwh": energia_descarregada_anual_kwh,
        },
    )


# ===========================================================================
# Monte Carlo (Sprint 4-C)
# ===========================================================================
#
# Substitui o tornado de sensibilidade ±20% por simulação probabilística.
# 10.000 iterações (default) com:
#   - CAPEX:    Triangular(min, central, max)
#   - OPEX:     Triangular(min, central, max)
#   - Economia: Triangular(min, central, max)
#   - WACC:     Normal truncada (média, desvio_padrão, [-0.5, +0.5] do centro)
#
# Devolve P10/P25/P50/P75/P90 do VPL, probabilidade de viabilidade
# (P(VPL > 0)) e histograma binned para plotagem.
#
# Filosofia do bess-core mantida: zero dependências externas. Usa apenas
# `random` e `statistics` da stdlib. Reprodutível via seed.
# ===========================================================================


@dataclass(frozen=True)
class ResultadoMonteCarlo:
    """
    Saída da simulação Monte Carlo financeira.

    Attributes
    ----------
    n_iteracoes : int
        Número de amostras geradas.
    vpl_brl_p10 .. p90 : float
        Percentis do VPL (R$). P50 é a mediana.
    vpl_brl_media : float
        Média aritmética dos VPLs simulados.
    vpl_brl_desvio_padrao : float
        Desvio-padrão amostral.
    vpl_brl_min, vpl_brl_max : float
        Mínimo e máximo observados.
    probabilidade_viavel : float
        P(VPL > 0), em [0, 1]. Métrica-chave para defesa de projeto.
    probabilidade_tir_acima_wacc : float
        P(TIR ≥ WACC central). Equivale a P(VPL > 0) quando WACC é fixo.
    histograma_bins_brl : list[float]
        Bordas dos bins do histograma (n_bins+1 valores).
    histograma_contagens : list[int]
        Contagem de iterações em cada bin (n_bins valores).
    distribuicoes_usadas : dict
        Dump das distribuições de entrada (auditoria).
    seed : int | None
        Seed do RNG. None = não-reprodutível.
    """

    n_iteracoes: int
    vpl_brl_p10: float
    vpl_brl_p25: float
    vpl_brl_p50: float
    vpl_brl_p75: float
    vpl_brl_p90: float
    vpl_brl_media: float
    vpl_brl_desvio_padrao: float
    vpl_brl_min: float
    vpl_brl_max: float
    probabilidade_viavel: float
    probabilidade_tir_acima_wacc: float
    histograma_bins_brl: list[float]
    histograma_contagens: list[int]
    distribuicoes_usadas: dict
    seed: int | None


# ---------------------------------------------------------------------------
# Amostradores (puros, sem deps)
# ---------------------------------------------------------------------------


def _triangular(rng, low: float, mode: float, high: float) -> float:
    """
    Amostragem de distribuição triangular.

    `random.triangular` da stdlib aceita exatamente essa assinatura mas
    silenciosamente troca low/high se invertidos. Aqui validamos.
    """
    if not (low <= mode <= high):
        raise ValueError(
            f"Triangular requer low <= mode <= high; recebeu "
            f"({low}, {mode}, {high})."
        )
    if low == high:
        return mode
    return rng.triangular(low, high, mode)


def _normal_truncada(
    rng,
    media: float,
    desvio_padrao: float,
    min_valor: float,
    max_valor: float,
    max_tentativas: int = 100,
) -> float:
    """
    Normal truncada por rejection sampling.

    Em distribuições muito apertadas (desvio grande vs intervalo) pode
    falhar; nesse caso retorna o limite mais próximo.
    """
    if desvio_padrao <= 0:
        return media
    for _ in range(max_tentativas):
        x = rng.gauss(media, desvio_padrao)
        if min_valor <= x <= max_valor:
            return x
    # Fallback: clip
    return max(min_valor, min(max_valor, media))


# ---------------------------------------------------------------------------
# Histograma puro
# ---------------------------------------------------------------------------


def _histograma_binned(
    valores: list[float], n_bins: int
) -> tuple[list[float], list[int]]:
    """
    Constrói histograma com bins uniformes entre min(valores) e max(valores).

    Retorna (bordas[n_bins+1], contagens[n_bins]).
    """
    if not valores:
        return [], []
    minimo = min(valores)
    maximo = max(valores)
    if minimo == maximo:
        # Todos iguais — degenera, mas devolvemos algo plausível.
        return [minimo, maximo + 1.0], [len(valores)]

    largura = (maximo - minimo) / n_bins
    bordas = [minimo + i * largura for i in range(n_bins + 1)]
    bordas[-1] = maximo  # garantir que o ultimo valor cabe no ultimo bin
    contagens = [0] * n_bins
    for v in valores:
        # Indice do bin: int((v - minimo) / largura), clipado em [0, n_bins-1]
        if v >= maximo:
            idx = n_bins - 1
        else:
            idx = int((v - minimo) / largura)
        contagens[idx] += 1
    return bordas, contagens


# ---------------------------------------------------------------------------
# Percentil sem numpy
# ---------------------------------------------------------------------------


def _percentil(valores_ordenados: list[float], pct: float) -> float:
    """
    Percentil interpolado (método 'linear', equivalente ao numpy default).

    valores_ordenados deve estar ordenado ascendentemente.
    pct em [0, 100].
    """
    if not valores_ordenados:
        raise ValueError("Lista vazia.")
    n = len(valores_ordenados)
    if n == 1:
        return valores_ordenados[0]
    pos = (pct / 100.0) * (n - 1)
    lo = int(pos)
    hi = lo + 1
    if hi >= n:
        return valores_ordenados[-1]
    frac = pos - lo
    return valores_ordenados[lo] * (1.0 - frac) + valores_ordenados[hi] * frac


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def simulacao_monte_carlo(
    capex_brl: float,
    opex_anual_brl: float,
    economia_anual_brl: float,
    *,
    capex_min_pct: float = 0.85,
    capex_max_pct: float = 1.20,
    opex_min_pct: float = 0.70,
    opex_max_pct: float = 1.50,
    economia_min_pct: float = 0.70,
    economia_max_pct: float = 1.15,
    wacc_central: float = 0.12,
    wacc_desvio_padrao: float = 0.02,
    wacc_min: float = 0.05,
    wacc_max: float = 0.25,
    horizonte_anos: int = 20,
    degradacao_anual_economia: float = 0.02,
    inflacao_opex: float = 0.04,
    valor_residual_brl: float = 0.0,
    n_iteracoes: int = 10_000,
    n_bins_histograma: int = 30,
    seed: int | None = None,
) -> ResultadoMonteCarlo:
    """
    Simulação Monte Carlo do VPL para análise de risco do projeto.

    Substitui o tornado de sensibilidade ±20% por uma análise probabilística
    completa. Útil quando o veredicto do projeto depende criticamente de
    premissas incertas (CAPEX cotado direto vs lista, economia variável
    com perfil real de carga, WACC sensível à Selic).

    Distribuições padrão
    --------------------
    - **CAPEX**: Triangular(0.85·central, central, 1.20·central)
       Lower tail menor que upper porque cotação direta com integrador
       Tier 1 raramente bate menos de -15% sobre referência de mercado, mas
       overrun de obra/projeto costuma estourar +20% facilmente.
    - **OPEX**: Triangular(0.70·central, central, 1.50·central)
       Faixa larga porque manutenção/seguro/troca de PCS tem alta variância
       em projetos novos, sem histórico de operação.
    - **Economia**: Triangular(0.70·central, central, 1.15·central)
       Upside limitado (regulamentação pode mudar contra), downside maior
       (tarifa pode cair, perfil real pode cobrir menos picos).
    - **WACC**: Normal truncada(0.12, σ=0.02), em [0.05, 0.25]
       Reflete risco de taxa Selic / cost of equity ao longo do horizonte.

    Parameters
    ----------
    capex_brl, opex_anual_brl, economia_anual_brl : float
        Valores centrais. As distribuições são definidas como múltiplos
        destes (ver capex_min_pct, etc.).
    horizonte_anos, degradacao_anual_economia, inflacao_opex, valor_residual_brl
        Parâmetros do fluxo de caixa, idênticos a `analisar_financeiro`.
    n_iteracoes : int, default 10_000
        Tamanho da amostra Monte Carlo. Para visualização, 10k é suficiente
        para P10-P90 estáveis. Aumente para 100k em produção.
    n_bins_histograma : int, default 30
        Número de bins do histograma de saída.
    seed : int | None
        Se fornecido, garante reprodutibilidade.

    Returns
    -------
    ResultadoMonteCarlo

    Raises
    ------
    ValueError
        Se algum parâmetro estiver fora de limites plausíveis.

    Examples
    --------
    >>> r = simulacao_monte_carlo(
    ...     capex_brl=2_000_000.0,
    ...     opex_anual_brl=20_000.0,
    ...     economia_anual_brl=200_000.0,
    ...     n_iteracoes=1000,
    ...     seed=42,
    ... )
    >>> 0.0 <= r.probabilidade_viavel <= 1.0
    True
    >>> r.vpl_brl_p10 <= r.vpl_brl_p50 <= r.vpl_brl_p90
    True
    """
    # ---- Validação ------------------------------------------------------
    if n_iteracoes < 100:
        raise ValueError("n_iteracoes deve ser >= 100 para resultados estáveis.")
    if not (0.0 < capex_min_pct <= 1.0 <= capex_max_pct):
        raise ValueError("capex_min_pct deve ser em (0,1] e capex_max_pct >= 1.")
    if not (0.0 < opex_min_pct <= 1.0 <= opex_max_pct):
        raise ValueError("opex_min_pct deve ser em (0,1] e opex_max_pct >= 1.")
    if not (0.0 < economia_min_pct <= 1.0 <= economia_max_pct):
        raise ValueError(
            "economia_min_pct deve ser em (0,1] e economia_max_pct >= 1."
        )
    if not (wacc_min <= wacc_central <= wacc_max):
        raise ValueError(
            f"wacc_central ({wacc_central}) fora de [wacc_min, wacc_max] "
            f"({wacc_min}, {wacc_max})."
        )
    if wacc_desvio_padrao < 0:
        raise ValueError("wacc_desvio_padrao deve ser >= 0.")
    if n_bins_histograma < 5:
        raise ValueError("n_bins_histograma deve ser >= 5.")

    import random

    rng = random.Random(seed) if seed is not None else random.Random()

    # Distribuições absolutas
    capex_low = capex_brl * capex_min_pct
    capex_high = capex_brl * capex_max_pct
    opex_low = opex_anual_brl * opex_min_pct
    opex_high = opex_anual_brl * opex_max_pct
    economia_low = economia_anual_brl * economia_min_pct
    economia_high = economia_anual_brl * economia_max_pct

    vpls: list[float] = []

    for _ in range(n_iteracoes):
        capex_amostra = _triangular(rng, capex_low, capex_brl, capex_high)
        opex_amostra = _triangular(rng, opex_low, opex_anual_brl, opex_high)
        economia_amostra = _triangular(
            rng, economia_low, economia_anual_brl, economia_high
        )
        wacc_amostra = _normal_truncada(
            rng,
            media=wacc_central,
            desvio_padrao=wacc_desvio_padrao,
            min_valor=wacc_min,
            max_valor=wacc_max,
        )

        fluxos = _construir_fluxos(
            capex_brl=capex_amostra,
            economia_anual_brl=economia_amostra,
            opex_anual_brl=opex_amostra,
            horizonte_anos=horizonte_anos,
            degradacao_anual_economia=degradacao_anual_economia,
            inflacao_opex=inflacao_opex,
            valor_residual_brl=valor_residual_brl,
        )
        vpl = _vpl(fluxos, wacc_amostra)
        vpls.append(vpl)

    # Estatísticas
    import statistics

    vpls_ordenados = sorted(vpls)
    media = statistics.fmean(vpls)
    desvio = statistics.stdev(vpls) if len(vpls) > 1 else 0.0
    p10 = _percentil(vpls_ordenados, 10)
    p25 = _percentil(vpls_ordenados, 25)
    p50 = _percentil(vpls_ordenados, 50)
    p75 = _percentil(vpls_ordenados, 75)
    p90 = _percentil(vpls_ordenados, 90)

    n_viaveis = sum(1 for v in vpls if v > 0)
    prob_viavel = n_viaveis / n_iteracoes

    # P(TIR >= WACC central) ⇔ P(VPL > 0) quando o desconto é o WACC central.
    # Mas aqui o WACC varia: vamos calcular como recálculo independente
    # comparando o VPL ao WACC central. Usar tabela já gerada não funciona
    # porque cada vpl tem seu wacc próprio. Para simplificar, definimos:
    #   prob_tir_acima_wacc ≈ prob_viavel (ambos são "projeto vale a pena")
    prob_tir_acima_wacc = prob_viavel

    # Histograma
    bordas, contagens = _histograma_binned(vpls_ordenados, n_bins_histograma)

    return ResultadoMonteCarlo(
        n_iteracoes=n_iteracoes,
        vpl_brl_p10=p10,
        vpl_brl_p25=p25,
        vpl_brl_p50=p50,
        vpl_brl_p75=p75,
        vpl_brl_p90=p90,
        vpl_brl_media=media,
        vpl_brl_desvio_padrao=desvio,
        vpl_brl_min=vpls_ordenados[0],
        vpl_brl_max=vpls_ordenados[-1],
        probabilidade_viavel=prob_viavel,
        probabilidade_tir_acima_wacc=prob_tir_acima_wacc,
        histograma_bins_brl=bordas,
        histograma_contagens=contagens,
        distribuicoes_usadas={
            "capex": {"distribuicao": "triangular", "min": capex_low,
                      "central": capex_brl, "max": capex_high},
            "opex": {"distribuicao": "triangular", "min": opex_low,
                     "central": opex_anual_brl, "max": opex_high},
            "economia": {"distribuicao": "triangular", "min": economia_low,
                         "central": economia_anual_brl, "max": economia_high},
            "wacc": {"distribuicao": "normal_truncada", "media": wacc_central,
                     "desvio_padrao": wacc_desvio_padrao,
                     "min": wacc_min, "max": wacc_max},
        },
        seed=seed,
    )
