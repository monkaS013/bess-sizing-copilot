"""
dimensionamento.py
==================

Dimensionamento de Sistemas de Armazenamento de Energia (BESS) para diferentes
estratégias operacionais.

Sprint 1.1 entrega: peak shaving (corte de demanda) para C&I.

Referências normativas
----------------------
- ABNT NBR 16690:2019 — Instalações elétricas de arranjos fotovoltaicos.
- ABNT NBR 5410:2004  — Instalações elétricas de baixa tensão.
- IEC 62933-2-1:2017  — Electrical energy storage systems – Unit parameters.
- ANEEL REN 1.000/2021 — Regras gerais de fornecimento (demanda contratada).
- DOE/EPRI Energy Storage Handbook (2020) — Convenções de DoD, η_rt e derating.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionamentoBESS:
    """
    Resultado imutável do dimensionamento de um BESS.

    Attributes
    ----------
    energia_util_kwh : float
        Energia útil entregue à carga durante o pior evento de pico (kWh).
        É o que o cliente "vê" — descontadas as perdas de descarga.
    energia_nominal_kwh : float
        Capacidade nominal de placa do banco (kWh). Já incorpora DoD,
        eficiência de descarga e reserva técnica.
    potencia_kw : float
        Potência nominal do conversor/inversor (kW), com derating aplicado.
    c_rate : float
        Razão potência/energia nominal (1/h). Indica agressividade do banco
        (ex.: 0.5C → descarrega capacidade total em 2 h).
    p_shave_kw : float
        Potência máxima a cortar (P_carga_max − P_contratada), em kW.
    energia_evento_max_kwh : float
        Energia entregue no pior evento de pico **antes** do derating (kWh).
    n_eventos_pico : int
        Quantidade de eventos de pico identificados no perfil.
    premissas : dict
        Cópia dos parâmetros de entrada para auditoria.
    """

    energia_util_kwh: float
    energia_nominal_kwh: float
    potencia_kw: float
    c_rate: float
    p_shave_kw: float
    energia_evento_max_kwh: float
    n_eventos_pico: int
    premissas: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def dimensionar_peak_shaving(
    perfil_carga_horario: Sequence[float],
    demanda_contratada_kw: float,
    tarifa_demanda_brl_kw: float,
    dod: float = 0.9,
    eficiencia_rt: float = 0.92,
    reserva_tecnica: float = 0.1,
    delta_t_h: float = 1.0,
) -> DimensionamentoBESS:
    r"""
    Dimensiona um BESS para a estratégia de **peak shaving**.

    Peak shaving consiste em descarregar o banco quando a demanda da carga
    ultrapassa um patamar (tipicamente a demanda contratada), mantendo a
    leitura no medidor abaixo desse patamar e evitando ultrapassagens
    tarifadas (REN 1.000/2021, Art. 60).

    Modelo matemático
    -----------------
    Para cada instante :math:`t` discretizado em passos :math:`\Delta t`:

    .. math::

        P_{exc}(t) = \max\bigl( P_{carga}(t) - P_{contratada},\; 0 \bigr)

    Identificam-se *eventos de pico* — sequências contínuas onde
    :math:`P_{exc}(t) > 0`. Para cada evento :math:`k`:

    .. math::

        E_{evento,k} = \sum_{t \in k} P_{exc}(t) \cdot \Delta t

    A potência mínima do conversor é o pico máximo de excedente:

    .. math::

        P_{shave} = \max_t P_{exc}(t)

    A energia útil é o pior evento (assume-se recarga entre eventos):

    .. math::

        E_{util} = \max_k E_{evento,k}

    **Derating** — aplica DoD, perdas de descarga e reserva técnica.
    Considerando eficiência simétrica :math:`\eta_d = \sqrt{\eta_{rt}}`:

    .. math::

        E_{nominal} &= \frac{E_{util}}{\mathrm{DoD} \cdot \eta_d}
                       \cdot \bigl(1 + r_{tec}\bigr) \\[4pt]
        P_{nominal} &= \frac{P_{shave}}{\eta_d}
                       \cdot \bigl(1 + r_{tec}\bigr) \\[4pt]
        C_{rate}    &= \frac{P_{nominal}}{E_{nominal}}

    Premissas
    ---------
    - Perfil amostrado em intervalos uniformes de :math:`\Delta t` horas.
    - O banco recarrega entre eventos de pico (off-peak), portanto o pior
      evento isolado é que dimensiona a capacidade.
    - :math:`\eta_d = \eta_c = \sqrt{\eta_{rt}}` (simetria carga/descarga) —
      boa aproximação para LFP com inversores Huawei LUNA2000 / Sungrow.
    - Reserva técnica aplicada multiplicativamente sobre energia *e* potência.
    - Defaults (DoD=0.9, η_rt=0.92, reserva=0.10) alinhados com fichas
      técnicas Huawei LUNA2000-S0/S1 e CATL EnerOne.

    Parameters
    ----------
    perfil_carga_horario : Sequence[float]
        Demanda da carga ao longo do tempo, em kW. Tipicamente 24 (dia),
        168 (semana) ou 8760 (ano) amostras. Comprimento arbitrário aceito.
    demanda_contratada_kw : float
        Limiar de corte (kW). Demanda contratada com a distribuidora ou
        meta operacional definida pelo cliente.
    tarifa_demanda_brl_kw : float
        Tarifa de demanda aplicável (R$/kW). Registrada nas premissas para
        auditoria — não influencia o sizing nesta função.
    dod : float, default 0.9
        Profundidade de descarga útil (0 < dod ≤ 1).
    eficiencia_rt : float, default 0.92
        Eficiência round-trip (0 < η_rt ≤ 1).
    reserva_tecnica : float, default 0.1
        Margem de segurança aplicada multiplicativamente (≥ 0).
    delta_t_h : float, default 1.0
        Intervalo de amostragem do perfil, em horas (use 0.25 para 15 min).

    Returns
    -------
    DimensionamentoBESS
        Dataclass imutável com energia útil, energia nominal, potência,
        C-rate, contagem de eventos e premissas.

    Raises
    ------
    ValueError
        Se algum parâmetro estiver fora dos limites físicos plausíveis
        (DoD > 1, η > 1, perfil vazio etc.) ou se a carga jamais exceder
        a demanda contratada (peak shaving desnecessário).

    Examples
    --------
    Indústria com 500 kW contratados; pico de 650 kW por 2 h em um dia:

    >>> perfil = [500.0] * 24
    >>> perfil[14] = perfil[15] = 650.0
    >>> r = dimensionar_peak_shaving(perfil, 500.0, 23.50)
    >>> round(r.p_shave_kw, 1)
    150.0
    >>> round(r.energia_evento_max_kwh, 1)
    300.0
    >>> r.n_eventos_pico
    1
    """
    # -- Validação de entrada ------------------------------------------------
    if len(perfil_carga_horario) == 0:
        raise ValueError("perfil_carga_horario não pode ser vazio.")
    if demanda_contratada_kw <= 0:
        raise ValueError("demanda_contratada_kw deve ser > 0 kW.")
    if not (0.0 < dod <= 1.0):
        raise ValueError("DoD deve estar no intervalo (0, 1].")
    if not (0.0 < eficiencia_rt <= 1.0):
        raise ValueError("eficiência round-trip deve estar em (0, 1].")
    if reserva_tecnica < 0.0:
        raise ValueError("reserva_técnica não pode ser negativa.")
    if delta_t_h <= 0.0:
        raise ValueError("delta_t_h deve ser > 0 h.")
    if any(p < 0 for p in perfil_carga_horario):
        raise ValueError("perfil_carga_horario não pode conter valores negativos.")

    # -- Excedentes hora a hora ---------------------------------------------
    excedentes = [
        max(p - demanda_contratada_kw, 0.0) for p in perfil_carga_horario
    ]
    p_shave = max(excedentes)
    if p_shave <= 0.0:
        raise ValueError(
            "Carga nunca excede a demanda contratada — peak shaving "
            "desnecessário neste perfil."
        )

    # -- Identificação dos eventos de pico ---------------------------------
    # Um evento é uma sequência contígua de horas com excedente > 0.
    eventos_energia: list[float] = []
    energia_evento_atual = 0.0
    em_evento = False
    for e in excedentes:
        if e > 0.0:
            energia_evento_atual += e * delta_t_h
            em_evento = True
        elif em_evento:
            eventos_energia.append(energia_evento_atual)
            energia_evento_atual = 0.0
            em_evento = False
    if em_evento:  # evento aberto no final do perfil
        eventos_energia.append(energia_evento_atual)

    energia_evento_max = max(eventos_energia)
    n_eventos = len(eventos_energia)

    # -- Derating ----------------------------------------------------------
    eta_d = math.sqrt(eficiencia_rt)
    fator_reserva = 1.0 + reserva_tecnica

    energia_util = energia_evento_max  # entregue à carga durante o pico
    energia_nominal = energia_util / (dod * eta_d) * fator_reserva
    potencia_nominal = p_shave / eta_d * fator_reserva
    c_rate = potencia_nominal / energia_nominal

    return DimensionamentoBESS(
        energia_util_kwh=energia_util,
        energia_nominal_kwh=energia_nominal,
        potencia_kw=potencia_nominal,
        c_rate=c_rate,
        p_shave_kw=p_shave,
        energia_evento_max_kwh=energia_evento_max,
        n_eventos_pico=n_eventos,
        premissas={
            "demanda_contratada_kw": demanda_contratada_kw,
            "tarifa_demanda_brl_kw": tarifa_demanda_brl_kw,
            "dod": dod,
            "eficiencia_rt": eficiencia_rt,
            "eta_d_derivado": eta_d,
            "reserva_tecnica": reserva_tecnica,
            "delta_t_h": delta_t_h,
            "horas_amostradas": len(perfil_carga_horario),
        },
    )


# ===========================================================================
# Arbitragem (mercado livre)
# ===========================================================================


@dataclass(frozen=True)
class DimensionamentoArbitragem:
    """
    Resultado do dimensionamento para arbitragem temporal de energia.

    Attributes
    ----------
    energia_util_kwh : float
        Energia entregue ao mercado por descarga (kWh). = P x duracao.
    energia_nominal_kwh : float
        Capacidade nominal de placa (kWh), ja com DoD, eta_d e reserva.
    potencia_kw : float
        Potencia nominal do PCS/inversor (kW), com derating.
    c_rate : float
        Razao potencia/energia nominal (1/h).
    duracao_descarga_h : float
        Duracao da descarga a potencia nominal (h). Copia do input.
    energia_throughput_anual_kwh : float
        Energia descarregada por ano = E_util x ciclos_dia x 365.
    premissas : dict
        Copia dos parametros para auditoria.
    """

    energia_util_kwh: float
    energia_nominal_kwh: float
    potencia_kw: float
    c_rate: float
    duracao_descarga_h: float
    energia_throughput_anual_kwh: float
    premissas: dict = field(default_factory=dict)


def dimensionar_arbitragem(
    potencia_alvo_kw: float,
    duracao_descarga_h: float,
    ciclos_dia: float = 1.0,
    dod: float = 0.9,
    eficiencia_rt: float = 0.92,
    reserva_tecnica: float = 0.1,
) -> DimensionamentoArbitragem:
    """
    Dimensiona um BESS para arbitragem temporal no mercado livre (ACL).

    Modelo
    ------
        E_util      = P_alvo * t_desc
        eta_d       = sqrt(eta_rt)
        E_nominal   = E_util / (DoD * eta_d) * (1 + r_tec)
        P_nominal   = P_alvo / eta_d * (1 + r_tec)
        C_rate      = P_nominal / E_nominal
        Throughput  = E_util * ciclos_dia * 365

    Premissas
    ---------
    - 1 ciclo/dia tipico em arbitragem ACL diurna.
    - DoD 0.9 e eta_rt 0.92 sao Tier 1 LFP (Huawei, CATL).
    - Throughput anual deve ser comparado com garantia do fabricante.

    Examples
    --------
    >>> r = dimensionar_arbitragem(1000.0, 4.0)
    >>> round(r.energia_util_kwh, 0)
    4000.0
    """
    if potencia_alvo_kw <= 0:
        raise ValueError("potencia_alvo_kw deve ser > 0 kW.")
    if duracao_descarga_h <= 0:
        raise ValueError("duracao_descarga_h deve ser > 0 h.")
    if ciclos_dia <= 0:
        raise ValueError("ciclos_dia deve ser > 0.")
    if not (0.0 < dod <= 1.0):
        raise ValueError("DoD deve estar em (0, 1].")
    if not (0.0 < eficiencia_rt <= 1.0):
        raise ValueError("eficiencia round-trip deve estar em (0, 1].")
    if reserva_tecnica < 0.0:
        raise ValueError("reserva_tecnica nao pode ser negativa.")

    eta_d = math.sqrt(eficiencia_rt)
    fator_reserva = 1.0 + reserva_tecnica

    energia_util = potencia_alvo_kw * duracao_descarga_h
    energia_nominal = energia_util / (dod * eta_d) * fator_reserva
    potencia_nominal = potencia_alvo_kw / eta_d * fator_reserva
    c_rate = potencia_nominal / energia_nominal
    throughput_anual = energia_util * ciclos_dia * 365.0

    return DimensionamentoArbitragem(
        energia_util_kwh=energia_util,
        energia_nominal_kwh=energia_nominal,
        potencia_kw=potencia_nominal,
        c_rate=c_rate,
        duracao_descarga_h=duracao_descarga_h,
        energia_throughput_anual_kwh=throughput_anual,
        premissas={
            "potencia_alvo_kw": potencia_alvo_kw,
            "duracao_descarga_h": duracao_descarga_h,
            "ciclos_dia": ciclos_dia,
            "dod": dod,
            "eficiencia_rt": eficiencia_rt,
            "eta_d_derivado": eta_d,
            "reserva_tecnica": reserva_tecnica,
        },
    )


# ===========================================================================
# Backup (cargas criticas)
# ===========================================================================


@dataclass(frozen=True)
class DimensionamentoBackup:
    """
    Resultado do dimensionamento para backup de cargas criticas.

    Attributes
    ----------
    energia_util_kwh : float
        Energia entregue as cargas criticas durante o evento (kWh).
    energia_nominal_kwh : float
        Capacidade nominal de placa (kWh).
    potencia_kw : float
        Potencia nominal do PCS (kW), com derating.
    c_rate : float
        Razao potencia/energia nominal (1/h).
    autonomia_h : float
        Autonomia projetada a carga critica nominal (h).
    premissas : dict
        Copia dos parametros para auditoria.
    """

    energia_util_kwh: float
    energia_nominal_kwh: float
    potencia_kw: float
    c_rate: float
    autonomia_h: float
    premissas: dict = field(default_factory=dict)


def dimensionar_backup(
    carga_critica_kw: float,
    autonomia_h: float,
    dod: float = 0.95,
    eficiencia_rt: float = 0.92,
    reserva_tecnica: float = 0.20,
) -> DimensionamentoBackup:
    """
    Dimensiona um BESS para backup de cargas criticas (UPS-like).

    Aplicacoes tipicas: hospitais (CTI, centro cirurgico), data centers,
    industrias de processo continuo. Defaults mais conservadores que
    peak shaving:
    - DoD 0.95: prioriza continuidade da carga em emergencia.
    - Reserva 0.20: incerteza sobre duracao real do evento e degradacao.
    - Sem recarga durante o evento: dimensionamento monolitico.

    Modelo
    ------
        E_util      = P_critica * t_aut
        eta_d       = sqrt(eta_rt)
        E_nominal   = E_util / (DoD * eta_d) * (1 + r_tec)
        P_nominal   = P_critica / eta_d * (1 + r_tec)

    Examples
    --------
    >>> r = dimensionar_backup(100.0, 4.0)
    >>> r.energia_util_kwh
    400.0
    """
    if carga_critica_kw <= 0:
        raise ValueError("carga_critica_kw deve ser > 0 kW.")
    if autonomia_h <= 0:
        raise ValueError("autonomia_h deve ser > 0 h.")
    if not (0.0 < dod <= 1.0):
        raise ValueError("DoD deve estar em (0, 1].")
    if not (0.0 < eficiencia_rt <= 1.0):
        raise ValueError("eficiencia round-trip deve estar em (0, 1].")
    if reserva_tecnica < 0.0:
        raise ValueError("reserva_tecnica nao pode ser negativa.")

    eta_d = math.sqrt(eficiencia_rt)
    fator_reserva = 1.0 + reserva_tecnica

    energia_util = carga_critica_kw * autonomia_h
    energia_nominal = energia_util / (dod * eta_d) * fator_reserva
    potencia_nominal = carga_critica_kw / eta_d * fator_reserva
    c_rate = potencia_nominal / energia_nominal

    return DimensionamentoBackup(
        energia_util_kwh=energia_util,
        energia_nominal_kwh=energia_nominal,
        potencia_kw=potencia_nominal,
        c_rate=c_rate,
        autonomia_h=autonomia_h,
        premissas={
            "carga_critica_kw": carga_critica_kw,
            "autonomia_h": autonomia_h,
            "dod": dod,
            "eficiencia_rt": eficiencia_rt,
            "eta_d_derivado": eta_d,
            "reserva_tecnica": reserva_tecnica,
        },
    )
