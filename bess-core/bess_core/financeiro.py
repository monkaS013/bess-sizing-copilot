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
