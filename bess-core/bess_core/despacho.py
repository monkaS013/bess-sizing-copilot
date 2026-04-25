"""
despacho.py
===========

Simulação horária do despacho do BESS sobre um horizonte de operação
(tipicamente 8760 h = 1 ano típico, mas suporta recortes arbitrários).

Sprint 1.2 entrega: 3 estratégias via dispatch heurístico determinístico.

Estratégias suportadas
----------------------
- ``peak_shaving``        : descarrega quando carga > threshold; recarrega
                            quando há folga sob o threshold.
- ``arbitragem``          : carrega em horários de preço baixo (≤ percentil
                            de carga); descarrega em preços altos (≥ percentil
                            de descarga).
- ``autoconsumo_hibrido`` : carrega do excedente FV; descarrega para cobrir
                            déficit (FV < carga).

Convenções
----------
- SoC ∈ [0, 1] mede capacidade DC nominal. SoC = 1 ⇒ E_nominal kWh DC.
- ``p_carga[t]`` : potência AC que flui da rede (ou FV) para o sistema BESS
                   (medida no medidor / inversor).
- ``p_descarga[t]`` : potência AC que flui do BESS para a carga.
- η_c = η_d = √η_rt (eficiência simétrica carga/descarga).
- Atualização DC do SoC:

      SoC[t+1] = SoC[t] + (p_carga[t]·η_c - p_descarga[t]/η_d)·Δt / E_nominal

- ``p_grid[t]`` = p_carga[t] + p_load[t] - p_descarga[t] - p_fv[t]
                 (positivo = importa da rede; negativo = exporta).

Defesa heurístico vs LP
-----------------------
Para *peak shaving* e *autoconsumo* a dispatch greedy é provadamente ótima
(problema sem dependência temporal das decisões — corte máximo possível em
cada hora é independente das demais quando há recarga garantida off-peak).
Para *arbitragem* o greedy por percentil é subótimo vs LP com previsão
perfeita; documentado como limitação aceitável da Sprint 1.2 (LP via cvxpy
fica para uma evolução opcional, sem bloqueio do MVP).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Sequence


Estrategia = Literal["peak_shaving", "arbitragem", "autoconsumo_hibrido"]


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoDespacho:
    """
    Resultado horário da simulação de despacho.

    Attributes
    ----------
    soc : list[float]
        SoC ao início de cada passo + 1 valor final. Comprimento = N+1.
    p_carga_kw : list[float]
        Potência AC de carga (≥ 0) em cada passo. Comprimento = N.
    p_descarga_kw : list[float]
        Potência AC de descarga (≥ 0) em cada passo. Comprimento = N.
    p_grid_kw : list[float]
        Fluxo líquido pelo medidor (kW). Positivo = import; negativo = export.
    demanda_apos_bess_kw : list[float]
        Demanda residual vista pelo medidor após ação do BESS (kW).
    energia_carregada_kwh : float
        Σ p_carga·Δt — energia AC drenada para o banco (kWh).
    energia_descarregada_kwh : float
        Σ p_descarga·Δt — energia AC entregue pelo banco (kWh).
    energia_grid_importada_kwh : float
        Σ max(p_grid, 0)·Δt — energia importada da rede (kWh).
    energia_grid_exportada_kwh : float
        Σ max(-p_grid, 0)·Δt — energia exportada para a rede (kWh).
    ciclos_equivalentes : float
        Ciclos completos equivalentes (energia DC entregue / E_nominal).
    perdas_kwh : float
        Perdas térmicas (carga + descarga), em kWh.
    delta_soc : float
        SoC_final − SoC_inicial (energia residual no banco).
    premissas : dict
        Cópia dos parâmetros de entrada para auditoria.
    """

    soc: list[float]
    p_carga_kw: list[float]
    p_descarga_kw: list[float]
    p_grid_kw: list[float]
    demanda_apos_bess_kw: list[float]
    energia_carregada_kwh: float
    energia_descarregada_kwh: float
    energia_grid_importada_kwh: float
    energia_grid_exportada_kwh: float
    ciclos_equivalentes: float
    perdas_kwh: float
    delta_soc: float
    premissas: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Decisões por estratégia
# ---------------------------------------------------------------------------


def _limites_potencia(
    soc: float,
    soc_min: float,
    soc_max: float,
    p_nom: float,
    e_nom: float,
    eta_c: float,
    eta_d: float,
    dt: float,
) -> tuple[float, float]:
    """Retorna (p_carga_max, p_descarga_max) admissíveis no passo atual.

    Limita pela potência nominal e pela energia disponível/espaço no banco.
    """
    # Espaço disponível para carregar (DC) e energia equivalente AC.
    e_dc_espaco = max(soc_max - soc, 0.0) * e_nom
    p_carga_max = min(p_nom, e_dc_espaco / (eta_c * dt) if dt > 0 else 0.0)

    # Energia disponível para descarregar (DC) e equivalente AC.
    e_dc_disponivel = max(soc - soc_min, 0.0) * e_nom
    p_descarga_max = min(p_nom, e_dc_disponivel * eta_d / dt if dt > 0 else 0.0)

    return p_carga_max, p_descarga_max


def _decisao_peak_shaving(
    p_load: float,
    soc: float,
    threshold_kw: float,
    p_carga_max: float,
    p_descarga_max: float,
    headroom_carga_frac: float = 1.0,
) -> tuple[float, float]:
    """Greedy: descarrega o excedente sobre threshold; recarrega na folga."""
    excedente = max(p_load - threshold_kw, 0.0)
    if excedente > 0.0:
        p_d = min(excedente, p_descarga_max)
        return 0.0, p_d
    headroom = max(threshold_kw - p_load, 0.0) * headroom_carga_frac
    p_c = min(headroom, p_carga_max)
    return p_c, 0.0


def _decisao_arbitragem(
    preco: float,
    soc: float,
    p_carga_max: float,
    p_descarga_max: float,
    percentil_carga: float,
    percentil_descarga: float,
) -> tuple[float, float]:
    """Greedy por percentil: carrega quando barato, descarrega quando caro."""
    if preco <= percentil_carga:
        return p_carga_max, 0.0
    if preco >= percentil_descarga:
        return 0.0, p_descarga_max
    return 0.0, 0.0


def _decisao_autoconsumo(
    p_load: float,
    p_fv: float,
    soc: float,
    p_carga_max: float,
    p_descarga_max: float,
) -> tuple[float, float]:
    """Greedy: carrega do excedente FV; descarrega no déficit."""
    excedente_fv = max(p_fv - p_load, 0.0)
    deficit = max(p_load - p_fv, 0.0)
    if excedente_fv > 0.0:
        p_c = min(excedente_fv, p_carga_max)
        return p_c, 0.0
    if deficit > 0.0:
        p_d = min(deficit, p_descarga_max)
        return 0.0, p_d
    return 0.0, 0.0


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def simular_despacho_horario(
    perfil_carga_kw: Sequence[float],
    capacidade_nominal_kwh: float,
    potencia_kw: float,
    estrategia: Estrategia = "peak_shaving",
    *,
    perfil_fv_kw: Sequence[float] | None = None,
    tarifa_horaria_brl_kwh: Sequence[float] | None = None,
    threshold_kw: float | None = None,
    percentil_carga: float = 0.25,
    percentil_descarga: float = 0.75,
    soc_inicial: float = 0.5,
    dod: float = 0.9,
    eficiencia_rt: float = 0.92,
    delta_t_h: float = 1.0,
) -> ResultadoDespacho:
    """
    Simula o despacho horário do BESS sobre um horizonte arbitrário.

    Parameters
    ----------
    perfil_carga_kw : Sequence[float]
        Demanda da carga em cada passo (kW). Comprimento N.
    capacidade_nominal_kwh : float
        Capacidade nominal DC do banco (kWh).
    potencia_kw : float
        Potência nominal do PCS/inversor (kW).
    estrategia : {'peak_shaving', 'arbitragem', 'autoconsumo_hibrido'}
        Política de despacho.
    perfil_fv_kw : Sequence[float], opcional
        Geração FV em cada passo (kW). Obrigatório para autoconsumo_hibrido.
    tarifa_horaria_brl_kwh : Sequence[float], opcional
        Preço horário (R$/kWh). Obrigatório para arbitragem.
    threshold_kw : float, opcional
        Limiar de corte para peak shaving (kW). Obrigatório para peak_shaving.
    percentil_carga, percentil_descarga : float
        Percentis de preço usados em arbitragem (default 0.25 / 0.75).
    soc_inicial : float, default 0.5
        SoC ao início da simulação (0–1).
    dod : float, default 0.9
        Profundidade de descarga útil; soc_min = 1 - dod.
    eficiencia_rt : float, default 0.92
        η round-trip; η_c = η_d = √η_rt.
    delta_t_h : float, default 1.0
        Passo de simulação em horas.

    Returns
    -------
    ResultadoDespacho

    Raises
    ------
    ValueError
        Se parâmetros obrigatórios da estratégia escolhida estiverem ausentes
        ou inconsistentes (perfis com tamanhos diferentes, SoC fora de bounds,
        etc.).
    """
    # ---- Validação de entrada -------------------------------------------
    n = len(perfil_carga_kw)
    if n == 0:
        raise ValueError("perfil_carga_kw nao pode ser vazio.")
    if capacidade_nominal_kwh <= 0:
        raise ValueError("capacidade_nominal_kwh deve ser > 0 kWh.")
    if potencia_kw <= 0:
        raise ValueError("potencia_kw deve ser > 0 kW.")
    if not (0.0 < dod <= 1.0):
        raise ValueError("DoD deve estar em (0, 1].")
    if not (0.0 < eficiencia_rt <= 1.0):
        raise ValueError("eficiencia_rt deve estar em (0, 1].")
    if delta_t_h <= 0.0:
        raise ValueError("delta_t_h deve ser > 0 h.")
    soc_min = 1.0 - dod
    soc_max = 1.0
    if not (soc_min <= soc_inicial <= soc_max):
        raise ValueError(
            f"soc_inicial={soc_inicial} fora de [{soc_min}, {soc_max}]."
        )

    if estrategia == "peak_shaving":
        if threshold_kw is None:
            raise ValueError("threshold_kw e obrigatorio para peak_shaving.")
        if threshold_kw <= 0:
            raise ValueError("threshold_kw deve ser > 0 kW.")
    elif estrategia == "arbitragem":
        if tarifa_horaria_brl_kwh is None:
            raise ValueError(
                "tarifa_horaria_brl_kwh e obrigatorio para arbitragem."
            )
        if len(tarifa_horaria_brl_kwh) != n:
            raise ValueError(
                "tarifa_horaria_brl_kwh deve ter o mesmo comprimento de "
                "perfil_carga_kw."
            )
        if not (0.0 <= percentil_carga < percentil_descarga <= 1.0):
            raise ValueError(
                "percentil_carga deve ser < percentil_descarga em [0, 1]."
            )
    elif estrategia == "autoconsumo_hibrido":
        if perfil_fv_kw is None:
            raise ValueError(
                "perfil_fv_kw e obrigatorio para autoconsumo_hibrido."
            )
        if len(perfil_fv_kw) != n:
            raise ValueError(
                "perfil_fv_kw deve ter o mesmo comprimento de perfil_carga_kw."
            )
    else:
        raise ValueError(f"estrategia '{estrategia}' nao suportada.")

    if perfil_fv_kw is not None and len(perfil_fv_kw) != n:
        raise ValueError(
            "perfil_fv_kw deve ter o mesmo comprimento de perfil_carga_kw."
        )

    # ---- Pré-cálculos ----------------------------------------------------
    eta_c = math.sqrt(eficiencia_rt)
    eta_d = math.sqrt(eficiencia_rt)
    fv = list(perfil_fv_kw) if perfil_fv_kw is not None else [0.0] * n
    precos = (
        list(tarifa_horaria_brl_kwh) if tarifa_horaria_brl_kwh is not None else None
    )

    # Percentis de preço para arbitragem (calculados uma vez sobre o horizonte).
    percentil_carga_brl: float | None = None
    percentil_descarga_brl: float | None = None
    if estrategia == "arbitragem" and precos is not None:
        ordenado = sorted(precos)
        percentil_carga_brl = _percentil(ordenado, percentil_carga)
        percentil_descarga_brl = _percentil(ordenado, percentil_descarga)

    # ---- Loop de simulação ----------------------------------------------
    soc_seq: list[float] = [soc_inicial]
    p_carga_seq: list[float] = []
    p_descarga_seq: list[float] = []
    p_grid_seq: list[float] = []
    demanda_apos_seq: list[float] = []

    for t in range(n):
        soc_t = soc_seq[-1]
        p_load = perfil_carga_kw[t]
        p_fv_t = fv[t]

        p_carga_max, p_descarga_max = _limites_potencia(
            soc_t, soc_min, soc_max, potencia_kw,
            capacidade_nominal_kwh, eta_c, eta_d, delta_t_h,
        )

        if estrategia == "peak_shaving":
            p_c, p_d = _decisao_peak_shaving(
                p_load, soc_t, threshold_kw,
                p_carga_max, p_descarga_max,
            )
        elif estrategia == "arbitragem":
            assert precos is not None
            assert percentil_carga_brl is not None
            assert percentil_descarga_brl is not None
            p_c, p_d = _decisao_arbitragem(
                precos[t], soc_t,
                p_carga_max, p_descarga_max,
                percentil_carga_brl, percentil_descarga_brl,
            )
        else:  # autoconsumo_hibrido
            p_c, p_d = _decisao_autoconsumo(
                p_load, p_fv_t, soc_t,
                p_carga_max, p_descarga_max,
            )

        # Atualização do SoC (DC).
        delta_dc = (p_c * eta_c - p_d / eta_d) * delta_t_h
        soc_t1 = soc_t + delta_dc / capacidade_nominal_kwh
        # Clipping numérico defensivo (não deve ocorrer dado o limitador).
        soc_t1 = max(soc_min, min(soc_max, soc_t1))

        # p_grid: positivo = import, negativo = export.
        # Premissa: FV alimenta carga primeiro; sobra vai p/ banco ou rede.
        # p_grid = p_load + p_carga - p_descarga - p_fv
        p_grid_t = p_load + p_c - p_d - p_fv_t

        soc_seq.append(soc_t1)
        p_carga_seq.append(p_c)
        p_descarga_seq.append(p_d)
        p_grid_seq.append(p_grid_t)
        demanda_apos_seq.append(max(p_load - p_d, 0.0))

    # ---- Métricas agregadas ---------------------------------------------
    e_carregada = sum(p_carga_seq) * delta_t_h
    e_descarregada = sum(p_descarga_seq) * delta_t_h
    e_grid_imp = sum(max(g, 0.0) for g in p_grid_seq) * delta_t_h
    e_grid_exp = sum(max(-g, 0.0) for g in p_grid_seq) * delta_t_h

    # Ciclos equivalentes baseados no DC throughput.
    e_dc_descarregada = e_descarregada / eta_d if eta_d > 0 else 0.0
    ciclos_eq = e_dc_descarregada / capacidade_nominal_kwh

    # Perdas: carga (1-η_c) + descarga (1-η_d)/η_d.
    perdas_carga = e_carregada * (1.0 - eta_c)
    perdas_descarga = e_descarregada * (1.0 - eta_d) / eta_d
    perdas = perdas_carga + perdas_descarga

    delta_soc = soc_seq[-1] - soc_inicial

    return ResultadoDespacho(
        soc=soc_seq,
        p_carga_kw=p_carga_seq,
        p_descarga_kw=p_descarga_seq,
        p_grid_kw=p_grid_seq,
        demanda_apos_bess_kw=demanda_apos_seq,
        energia_carregada_kwh=e_carregada,
        energia_descarregada_kwh=e_descarregada,
        energia_grid_importada_kwh=e_grid_imp,
        energia_grid_exportada_kwh=e_grid_exp,
        ciclos_equivalentes=ciclos_eq,
        perdas_kwh=perdas,
        delta_soc=delta_soc,
        premissas={
            "estrategia": estrategia,
            "capacidade_nominal_kwh": capacidade_nominal_kwh,
            "potencia_kw": potencia_kw,
            "soc_inicial": soc_inicial,
            "dod": dod,
            "soc_min": soc_min,
            "soc_max": soc_max,
            "eficiencia_rt": eficiencia_rt,
            "eta_c": eta_c,
            "eta_d": eta_d,
            "delta_t_h": delta_t_h,
            "horizonte_passos": n,
            "horizonte_horas": n * delta_t_h,
            "threshold_kw": threshold_kw,
            "percentil_carga": percentil_carga if estrategia == "arbitragem" else None,
            "percentil_descarga": percentil_descarga if estrategia == "arbitragem" else None,
            "percentil_carga_brl": percentil_carga_brl,
            "percentil_descarga_brl": percentil_descarga_brl,
        },
    )


def _percentil(valores_ordenados: list[float], p: float) -> float:
    """Percentil tipo numpy.percentile com interpolacao linear."""
    if not valores_ordenados:
        raise ValueError("lista vazia.")
    if len(valores_ordenados) == 1:
        return valores_ordenados[0]
    k = p * (len(valores_ordenados) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return valores_ordenados[int(k)]
    return valores_ordenados[f] + (k - f) * (
        valores_ordenados[c] - valores_ordenados[f]
    )
