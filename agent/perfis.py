"""
perfis.py - Geradores de perfil de carga sintetico para casos comuns.

Util quando o usuario nao tem medicao horaria detalhada e descreve o
perfil em linguagem natural ("industria com pico de 650 kW por 2h ...").
"""

from __future__ import annotations

from typing import Sequence


def perfil_industrial_semanal(
    base_dia_util_kw: float,
    base_fim_semana_kw: float,
    pico_kw: float,
    hora_inicio_pico: int,
    duracao_pico_h: int,
    dias_uteis: int = 5,
) -> list[float]:
    """
    Gera 168 horas de perfil tipico industrial.

    Parameters
    ----------
    base_dia_util_kw : float
        Carga base em dia util (fora do pico).
    base_fim_semana_kw : float
        Carga base no fim de semana.
    pico_kw : float
        Carga durante o pico (em dia util).
    hora_inicio_pico : int
        Hora do dia em que o pico comeca (0-23).
    duracao_pico_h : int
        Duracao do pico em horas.
    dias_uteis : int, default 5
        Quantidade de dias uteis na semana.
    """
    perfil: list[float] = []
    for dia in range(7):
        if dia < dias_uteis:
            base = [base_dia_util_kw] * 24
            for h in range(hora_inicio_pico, hora_inicio_pico + duracao_pico_h):
                if 0 <= h < 24:
                    base[h] = pico_kw
        else:
            base = [base_fim_semana_kw] * 24
        perfil.extend(base)
    return perfil


def perfil_comercial_semanal(
    consumo_diurno_kw: float,
    consumo_noturno_kw: float,
    hora_abre: int = 8,
    hora_fecha: int = 18,
) -> list[float]:
    """Perfil tipico de comercio/escritorio com horario fixo."""
    perfil: list[float] = []
    for dia in range(7):
        for h in range(24):
            if dia < 5 and hora_abre <= h < hora_fecha:
                perfil.append(consumo_diurno_kw)
            else:
                perfil.append(consumo_noturno_kw)
    return perfil


def replicar_para_ano(perfil_semanal: Sequence[float]) -> list[float]:
    """Replica um perfil semanal (168h) para 8760h (1 ano)."""
    if len(perfil_semanal) != 168:
        raise ValueError("Perfil semanal deve ter 168 horas.")
    # 8760 / 168 = 52.14 semanas -> repetimos 52 + 24h
    base = list(perfil_semanal) * 52
    base.extend(perfil_semanal[:24])  # mais um dia para fechar 8760
    return base[:8760]


def curva_fv_diaria(
    potencia_kwp: float,
    hora_nascer: int = 6,
    hora_por: int = 18,
    fator_capacidade: float = 0.20,
) -> list[float]:
    """
    Curva FV simplificada: senoidal entre nascer e por do sol.

    fator_capacidade tipico no BR: 0.18 (Sul) a 0.22 (NE).
    """
    import math
    fv: list[float] = []
    duracao = hora_por - hora_nascer
    pico_kw = potencia_kwp  # potencia maxima ~ kWp em condicao standard
    for h in range(24):
        if hora_nascer <= h < hora_por:
            # senoidal: pico no meio do periodo
            fase = (h - hora_nascer + 0.5) / duracao * math.pi
            fv.append(pico_kw * math.sin(fase))
        else:
            fv.append(0.0)
    # Ajuste para fator de capacidade desejado (proporcionalmente)
    soma = sum(fv)
    soma_alvo = potencia_kwp * 24 * fator_capacidade
    if soma > 0:
        ratio = soma_alvo / soma
        fv = [v * ratio for v in fv]
    return fv
