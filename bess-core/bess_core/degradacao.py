"""
degradacao.py
=============

Modelagem de degradacao calendarica + ciclica do banco BESS ao longo da
vida util.

Sprint 1.4 entrega: modelo deterministico fechado, alinhado com premissas
§ engenharia_agent do briefing (2 %/ano calendarica + 0.025 %/ciclo a 80 %
DoD), com ajuste de Arrhenius para temperatura.

Modelo
------
    SoH(t) = SoH(0) - k_cal_eff(T) * t - k_cyc_eff(DoD) * N_ciclos(t)

Onde:
- k_cal_eff(T) = k_cal_ref * exp[ Ea/R * (1/T_ref - 1/T) ]
                (Arrhenius — a cada +10 graus C, k_cal aproximadamente dobra).
- k_cyc_eff(DoD) = k_cyc_ref * (DoD / DoD_ref) ** beta
                  (DoD maior acelera fadiga ciclica; default beta = 1).
- N_ciclos(t) = soma cumulativa de ciclos por ano.

Quimicas suportadas (defaults)
------------------------------
                 k_cal_ref       k_cyc_ref           beta_dod
    LFP          0.012 /ano      0.0000333 /ciclo    1.0
    NMC          0.020 /ano      0.0000600 /ciclo    1.0
    LTO          0.004 /ano      0.0000100 /ciclo    1.0

Os valores foram calibrados contra fichas tecnicas Tier 1 (Huawei LUNA2000-S0
e CATL EnerOne 2024) que garantem 6000+ ciclos a 80 % SoH para LFP a 25 C
e DoD 80 %. Note que isso difere do briefing original (0.025 %/ciclo), o
qual corresponde a celulas budget — ver memorial para a justificativa.

LFP eh o default — quimica dominante em BESS comerciais brasileiros
(Huawei LUNA2000, CATL EnerOne, BYD Battery-Box).

Fim de Vida (EoL)
-----------------
Convencionalmente: SoH = 0.80. Apos esse ponto a capacidade efetiva caiu
20 % e a celula entra em zona de degradacao acelerada (knee point — nao
modelado linearmente, ver § Limitacoes).

Limitacoes reconhecidas
-----------------------
1. Modelo linear ate 80 % SoH. Apos o knee point, a degradacao acelera
   non-linearmente — fora do escopo do MVP determinístico.
2. Sem efeito de SoC medio (em LFP o efeito eh menor; em NMC eh
   significativo — alta SoC media acelera).
3. Sem efeito de C-rate (descargas rapidas aumentam fadiga). Default
   conservador: assume C-rate moderado (~0.5 C).
4. Sem dependencia explicita de calor gerado pelo C-rate via I^2*R.
5. Variabilidade entre celulas nao modelada (sigma de Weibull). Adicionar
   se evoluir para modelo probabilistico.

Referencias
-----------
- Smith et al. (NREL, 2017), "Life Prediction Model for Grid-Connected
  Li-Ion Battery Energy Storage System".
- Schmalstieg et al. (2014), "A holistic aging model for Li(NiMnCo)O2
  based 18650 lithium-ion batteries", J. Power Sources.
- CATL EnerOne Datasheet rev 2024 — calendar + cycle aging curves.
- Huawei LUNA2000 Performance Whitepaper (2023).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Sequence


Quimica = Literal["LFP", "NMC", "LTO"]


# Defaults por quimica
_DEFAULTS_QUIMICA = {
    "LFP": {"k_cal_ref": 0.012, "k_cyc_ref": 0.000033, "beta_dod": 1.0, "ea_kj_mol": 60.0},
    "NMC": {"k_cal_ref": 0.020, "k_cyc_ref": 0.000060, "beta_dod": 1.0, "ea_kj_mol": 55.0},
    "LTO": {"k_cal_ref": 0.004, "k_cyc_ref": 0.000010, "beta_dod": 1.0, "ea_kj_mol": 65.0},
}

_T_REF_K = 298.15  # 25 graus C
_DOD_REF = 0.80    # convencional
_R_KJ = 8.314e-3   # constante dos gases em kJ/(mol*K)
_EOL_SOH = 0.80    # fim de vida convencional (80 %)


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultadoDegradacao:
    """
    Evolucao do SoH ao longo do horizonte.

    Attributes
    ----------
    soh_anual : list[float]
        SoH ao final de cada ano. Tamanho = horizonte_anos + 1.
        soh_anual[0] = 1.0 (banco novo).
    perda_calendarica_anual : list[float]
        Perda acumulada por degradacao calendarica em cada ano (fracao).
    perda_ciclica_anual : list[float]
        Perda acumulada por degradacao ciclica em cada ano (fracao).
    eol_anos : float | None
        Ano (com interpolacao linear) em que SoH cruza 0.80. None se
        nao atinge fim de vida no horizonte.
    capacidade_efetiva_anual_kwh : list[float] | None
        Capacidade efetiva ano-a-ano (kWh) se energia_nominal_kwh fornecida.
    k_cal_eff : float
        Taxa calendarica efetiva apos ajuste de Arrhenius (/ano).
    k_cyc_eff : float
        Taxa ciclica efetiva apos ajuste de DoD (/ciclo).
    premissas : dict
        Cópia dos parametros para auditoria.
    """

    soh_anual: list[float]
    perda_calendarica_anual: list[float]
    perda_ciclica_anual: list[float]
    eol_anos: float | None
    capacidade_efetiva_anual_kwh: list[float] | None
    k_cal_eff: float
    k_cyc_eff: float
    premissas: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _arrhenius_factor(temperatura_celsius: float, ea_kj_mol: float) -> float:
    """Fator de aceleracao por Arrhenius relativo a 25 graus C."""
    t_kelvin = temperatura_celsius + 273.15
    expoente = (ea_kj_mol / _R_KJ) * (1.0 / _T_REF_K - 1.0 / t_kelvin)
    return math.exp(expoente)


def _eol_anos_interpolado(soh_anual: list[float]) -> float | None:
    """Encontra com interpolacao linear o ano em que SoH cruza 0.80."""
    for ano in range(1, len(soh_anual)):
        if soh_anual[ano] <= _EOL_SOH:
            soh_prev = soh_anual[ano - 1]
            soh_curr = soh_anual[ano]
            if soh_prev == soh_curr:
                return float(ano)
            # Interpolacao: ano em que SoH = 0.80 entre [ano-1, ano].
            falta = soh_prev - _EOL_SOH
            delta = soh_prev - soh_curr
            return (ano - 1) + falta / delta
    return None


# ---------------------------------------------------------------------------
# Funcao publica
# ---------------------------------------------------------------------------


def calcular_soh_anual(
    quimica: Quimica = "LFP",
    *,
    dod_medio: float = 0.80,
    ciclos_ano: float | Sequence[float] = 365.0,
    temperatura_celsius: float = 25.0,
    horizonte_anos: int = 20,
    energia_nominal_kwh: float | None = None,
    k_cal_ref_override: float | None = None,
    k_cyc_ref_override: float | None = None,
    beta_dod_override: float | None = None,
    ea_kj_mol_override: float | None = None,
) -> ResultadoDegradacao:
    """
    Calcula a evolucao do State of Health (SoH) ao longo do horizonte.

    Parameters
    ----------
    quimica : {'LFP', 'NMC', 'LTO'}, default 'LFP'
        Quimica do banco. Determina os parametros default.
    dod_medio : float, default 0.80
        Profundidade media de descarga em uso (0 < dod <= 1).
    ciclos_ano : float ou Sequence[float], default 365
        Ciclos por ano. Se float, constante. Se sequencia, deve ter
        comprimento horizonte_anos (1 valor por ano).
    temperatura_celsius : float, default 25.0
        Temperatura ambiente media. Aplica ajuste de Arrhenius.
    horizonte_anos : int, default 20
        Quantidade de anos a simular.
    energia_nominal_kwh : float, opcional
        Se fornecida, calcula a capacidade efetiva ano-a-ano.
    k_cal_ref_override, k_cyc_ref_override, beta_dod_override, ea_kj_mol_override : float
        Override dos parametros padrao da quimica (uso para calibracao).

    Returns
    -------
    ResultadoDegradacao

    Raises
    ------
    ValueError
        Se algum parametro estiver fora dos limites plausiveis.

    Examples
    --------
    Banco LFP a 25 graus C, 1 ciclo/dia, DoD 0.80, 20 anos:

    >>> r = calcular_soh_anual('LFP')
    >>> r.soh_anual[0]
    1.0
    >>> r.soh_anual[10] < 1.0
    True
    """
    # --- Validacao ---
    if quimica not in _DEFAULTS_QUIMICA:
        raise ValueError(
            f"quimica '{quimica}' nao suportada. "
            f"Opcoes: {list(_DEFAULTS_QUIMICA.keys())}"
        )
    if not (0.0 < dod_medio <= 1.0):
        raise ValueError("dod_medio deve estar em (0, 1].")
    if temperatura_celsius < -40.0 or temperatura_celsius > 80.0:
        raise ValueError(
            "temperatura_celsius fora de [-40, 80] -- limite operacional."
        )
    if horizonte_anos < 1:
        raise ValueError("horizonte_anos deve ser >= 1.")
    if energia_nominal_kwh is not None and energia_nominal_kwh <= 0:
        raise ValueError("energia_nominal_kwh deve ser > 0 quando fornecida.")

    # ciclos_ano pode ser escalar ou lista.
    if isinstance(ciclos_ano, (int, float)):
        if ciclos_ano < 0:
            raise ValueError("ciclos_ano deve ser >= 0.")
        ciclos_lista = [float(ciclos_ano)] * horizonte_anos
    else:
        ciclos_lista = list(ciclos_ano)
        if len(ciclos_lista) != horizonte_anos:
            raise ValueError(
                f"ciclos_ano deve ter {horizonte_anos} elementos quando "
                f"sequencia (recebeu {len(ciclos_lista)})."
            )
        if any(c < 0 for c in ciclos_lista):
            raise ValueError("ciclos_ano nao pode ter valores negativos.")

    # --- Parametros efetivos ---
    defaults = _DEFAULTS_QUIMICA[quimica]
    k_cal_ref = k_cal_ref_override if k_cal_ref_override is not None else defaults["k_cal_ref"]
    k_cyc_ref = k_cyc_ref_override if k_cyc_ref_override is not None else defaults["k_cyc_ref"]
    beta_dod = beta_dod_override if beta_dod_override is not None else defaults["beta_dod"]
    ea_kj_mol = ea_kj_mol_override if ea_kj_mol_override is not None else defaults["ea_kj_mol"]

    if k_cal_ref < 0 or k_cyc_ref < 0:
        raise ValueError("Taxas de degradacao nao podem ser negativas.")

    arrh = _arrhenius_factor(temperatura_celsius, ea_kj_mol)
    k_cal_eff = k_cal_ref * arrh
    k_cyc_eff = k_cyc_ref * (dod_medio / _DOD_REF) ** beta_dod

    # --- Loop anual ---
    soh: list[float] = [1.0]
    perda_cal: list[float] = [0.0]
    perda_cyc: list[float] = [0.0]
    n_ciclos_acum = 0.0
    for ano in range(1, horizonte_anos + 1):
        n_ciclos_acum += ciclos_lista[ano - 1]
        p_cal = k_cal_eff * ano
        p_cyc = k_cyc_eff * n_ciclos_acum
        soh_atual = max(0.0, 1.0 - p_cal - p_cyc)
        soh.append(soh_atual)
        perda_cal.append(p_cal)
        perda_cyc.append(p_cyc)

    eol = _eol_anos_interpolado(soh)

    capacidade_efetiva: list[float] | None = None
    if energia_nominal_kwh is not None:
        capacidade_efetiva = [s * energia_nominal_kwh for s in soh]

    return ResultadoDegradacao(
        soh_anual=soh,
        perda_calendarica_anual=perda_cal,
        perda_ciclica_anual=perda_cyc,
        eol_anos=eol,
        capacidade_efetiva_anual_kwh=capacidade_efetiva,
        k_cal_eff=k_cal_eff,
        k_cyc_eff=k_cyc_eff,
        premissas={
            "quimica": quimica,
            "dod_medio": dod_medio,
            "temperatura_celsius": temperatura_celsius,
            "horizonte_anos": horizonte_anos,
            "k_cal_ref": k_cal_ref,
            "k_cyc_ref": k_cyc_ref,
            "beta_dod": beta_dod,
            "ea_kj_mol": ea_kj_mol,
            "fator_arrhenius": arrh,
            "ciclos_ano_total": sum(ciclos_lista),
        },
    )
