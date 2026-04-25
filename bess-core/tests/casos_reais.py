"""
casos_reais.py
==============

Suite de validação consolidada — três casos reais do briefing BESS Sizing
Copilot, cada um com cálculo manual documentado e validado por pytest a 2 %
de tolerância.

Casos
-----
1. **Peak shaving industrial 500 kW** — corte de demanda contratada.
2. **Arbitragem mercado livre 1 MW** — banco de 4 h para ACL.
3. **Backup hospitalar 100 kW** — cargas críticas Grupo 1 (NBR 13534).

A planilha de cálculo manual está descrita em ``docs/CASOS_VALIDACAO.md``.

Convenções dos cálculos manuais
-------------------------------
- η_d = √η_rt (eficiência simétrica).
- Reserva técnica multiplicativa sobre energia E potência.
- Tolerância 2 % para todas as comparações (compatível com fichas técnicas).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from bess_core import (
    dimensionar_arbitragem,
    dimensionar_backup,
    dimensionar_peak_shaving,
)


TOLERANCIA = 0.02  # 2 %


def _aprox(obtido: float, esperado: float, tol: float = TOLERANCIA) -> bool:
    """Compara dois floats com tolerância relativa."""
    if esperado == 0.0:
        return abs(obtido) <= tol
    return abs(obtido - esperado) / abs(esperado) <= tol


@dataclass(frozen=True)
class ResultadoEsperado:
    """Valores calculados manualmente para o caso."""

    energia_util_kwh: float
    energia_nominal_kwh: float
    potencia_kw: float
    c_rate: float


# ============================================================================
# Caso 1 — Peak shaving industrial 500 kW
# ============================================================================
#
# Cenário:
#   - Indústria com 500 kW de demanda contratada
#   - Pico operacional de 650 kW por 2 h em 5 dias úteis (seg–sex, 14h–16h)
#   - Sáb/dom: 300 kW base (sem picos)
#   - Tarifa de demanda: R$ 23,50/kW
#   - Defaults: DoD=0.9, η_rt=0.92, reserva=0.10
#
# Cálculo manual:
#   P_shave  = 650 − 500                                = 150,00 kW
#   E_util   = 150 × 2                                  = 300,00 kWh
#   η_d      = √0.92                                    ≈ 0,9592
#   E_nom    = 300 / (0.9 × 0.9592) × 1.10              ≈ 382,18 kWh
#   P_nom    = 150 / 0.9592 × 1.10                      ≈ 172,04 kW
#   C-rate   = 172,04 / 382,18                          ≈ 0,450 1/h
# ============================================================================


PEAK_SHAVING_500KW_ESPERADO = ResultadoEsperado(
    energia_util_kwh=300.0,
    energia_nominal_kwh=382.18,
    potencia_kw=172.04,
    c_rate=0.450,
)


@pytest.fixture
def perfil_industrial_500kw() -> list[float]:
    """Semana de 168 h com 5 picos de 650 kW × 2 h."""
    perfil: list[float] = []
    for dia in range(7):
        if dia < 5:
            base = [500.0] * 24
            base[14] = 650.0
            base[15] = 650.0
        else:
            base = [300.0] * 24
        perfil.extend(base)
    return perfil


class TestCaso1PeakShavingIndustrial500kW:
    """Cenário industrial: 500 kW contratados, pico 650 kW × 2 h."""

    def test_energia_util(self, perfil_industrial_500kw):
        r = dimensionar_peak_shaving(perfil_industrial_500kw, 500.0, 23.50)
        assert _aprox(r.energia_util_kwh, PEAK_SHAVING_500KW_ESPERADO.energia_util_kwh)

    def test_energia_nominal(self, perfil_industrial_500kw):
        r = dimensionar_peak_shaving(perfil_industrial_500kw, 500.0, 23.50)
        assert _aprox(
            r.energia_nominal_kwh, PEAK_SHAVING_500KW_ESPERADO.energia_nominal_kwh
        )

    def test_potencia(self, perfil_industrial_500kw):
        r = dimensionar_peak_shaving(perfil_industrial_500kw, 500.0, 23.50)
        assert _aprox(r.potencia_kw, PEAK_SHAVING_500KW_ESPERADO.potencia_kw)

    def test_c_rate(self, perfil_industrial_500kw):
        r = dimensionar_peak_shaving(perfil_industrial_500kw, 500.0, 23.50)
        assert _aprox(r.c_rate, PEAK_SHAVING_500KW_ESPERADO.c_rate)

    def test_n_eventos_5_dias_uteis(self, perfil_industrial_500kw):
        r = dimensionar_peak_shaving(perfil_industrial_500kw, 500.0, 23.50)
        assert r.n_eventos_pico == 5

    def test_premissas_completas(self, perfil_industrial_500kw):
        r = dimensionar_peak_shaving(perfil_industrial_500kw, 500.0, 23.50)
        assert r.premissas["demanda_contratada_kw"] == 500.0
        assert r.premissas["tarifa_demanda_brl_kw"] == 23.50
        assert r.premissas["horas_amostradas"] == 168


# ============================================================================
# Caso 2 — Arbitragem mercado livre 1 MW
# ============================================================================
#
# Cenário:
#   - Cliente do ACL (Ambiente de Contratação Livre)
#   - Banco de 1 MW de potência alvo, descarga de 4 h (ESS de média duração)
#   - 1 ciclo/dia (compra madrugada, vende ponta)
#   - Defaults: DoD=0.9, η_rt=0.92, reserva=0.10
#
# Cálculo manual:
#   E_util       = 1000 × 4                              = 4 000,00 kWh
#   η_d          = √0.92                                 ≈ 0,9592
#   E_nominal    = 4000 / (0.9 × 0.9592) × 1.10          ≈ 5 095,77 kWh
#   P_nominal    = 1000 / 0.9592 × 1.10                  ≈ 1 146,93 kW
#   C-rate       = 1146,93 / 5095,77                     ≈ 0,225 1/h
#   Throughput   = 4000 × 1 × 365                        = 1 460 000 kWh/ano
#
# Comentário sobre garantia:
#   1 460 MWh/ano sobre 5 100 kWh nominais = ~286 ciclos/ano.
#   Datasheet típico Huawei LUNA2000-S0 garante 6 000 ciclos a 80 % SoH;
#   isto rende ~21 anos de operação — coerente com vida útil de planta.
# ============================================================================


ARBITRAGEM_1MW_ESPERADO = ResultadoEsperado(
    energia_util_kwh=4000.0,
    energia_nominal_kwh=5095.77,
    potencia_kw=1146.93,
    c_rate=0.225,
)


class TestCaso2ArbitragemACL1MW:
    """Cenário ACL: banco 1 MW × 4 h, 1 ciclo/dia."""

    def test_energia_util(self):
        r = dimensionar_arbitragem(potencia_alvo_kw=1000.0, duracao_descarga_h=4.0)
        assert _aprox(r.energia_util_kwh, ARBITRAGEM_1MW_ESPERADO.energia_util_kwh)

    def test_energia_nominal(self):
        r = dimensionar_arbitragem(1000.0, 4.0)
        assert _aprox(
            r.energia_nominal_kwh, ARBITRAGEM_1MW_ESPERADO.energia_nominal_kwh
        )

    def test_potencia(self):
        r = dimensionar_arbitragem(1000.0, 4.0)
        assert _aprox(r.potencia_kw, ARBITRAGEM_1MW_ESPERADO.potencia_kw)

    def test_c_rate(self):
        r = dimensionar_arbitragem(1000.0, 4.0)
        assert _aprox(r.c_rate, ARBITRAGEM_1MW_ESPERADO.c_rate)

    def test_throughput_anual_1_ciclo_dia(self):
        r = dimensionar_arbitragem(1000.0, 4.0, ciclos_dia=1.0)
        # 4 000 kWh × 1 × 365 = 1 460 000 kWh/ano
        assert _aprox(r.energia_throughput_anual_kwh, 1_460_000.0)

    def test_throughput_anual_2_ciclos_dia(self):
        r = dimensionar_arbitragem(1000.0, 4.0, ciclos_dia=2.0)
        # Dobra com 2 ciclos/dia
        assert _aprox(r.energia_throughput_anual_kwh, 2_920_000.0)

    def test_eta_d_derivado(self):
        r = dimensionar_arbitragem(1000.0, 4.0)
        assert math.isclose(r.premissas["eta_d_derivado"], math.sqrt(0.92))


# ============================================================================
# Caso 3 — Backup hospitalar 100 kW
# ============================================================================
#
# Cenário:
#   - Hospital com 100 kW de cargas críticas (CTI, centro cirúrgico, lab)
#   - Autonomia exigida: 4 h (cobertura entre falha da rede e partida do
#     gerador a diesel + transiente do gerador)
#   - Defaults backup: DoD=0.95, η_rt=0.92, reserva=0.20
#
# Cálculo manual:
#   E_util       = 100 × 4                               = 400,00 kWh
#   η_d          = √0.92                                 ≈ 0,9592
#   E_nominal    = 400 / (0.95 × 0.9592) × 1.20          ≈ 526,29 kWh
#   P_nominal    = 100 / 0.9592 × 1.20                   ≈ 125,11 kW
#   C-rate       = 125,11 / 526,29                       ≈ 0,238 1/h
#
# Observações:
#   - DoD 0.95 (vs 0.90 padrão) — em emergência, prioriza-se a continuidade
#     da carga sobre a longevidade da célula.
#   - Reserva 0.20 (vs 0.10 padrão) — incerteza maior sobre duração real do
#     evento e degradação ao longo de 10+ anos sem troca de células.
# ============================================================================


BACKUP_HOSPITALAR_100KW_ESPERADO = ResultadoEsperado(
    energia_util_kwh=400.0,
    energia_nominal_kwh=526.29,
    potencia_kw=125.11,
    c_rate=0.238,
)


class TestCaso3BackupHospitalar100kW:
    """Cenário hospitalar: 100 kW críticos × 4 h."""

    def test_energia_util(self):
        r = dimensionar_backup(carga_critica_kw=100.0, autonomia_h=4.0)
        assert _aprox(r.energia_util_kwh, BACKUP_HOSPITALAR_100KW_ESPERADO.energia_util_kwh)

    def test_energia_nominal(self):
        r = dimensionar_backup(100.0, 4.0)
        assert _aprox(
            r.energia_nominal_kwh,
            BACKUP_HOSPITALAR_100KW_ESPERADO.energia_nominal_kwh,
        )

    def test_potencia(self):
        r = dimensionar_backup(100.0, 4.0)
        assert _aprox(r.potencia_kw, BACKUP_HOSPITALAR_100KW_ESPERADO.potencia_kw)

    def test_c_rate(self):
        r = dimensionar_backup(100.0, 4.0)
        assert _aprox(r.c_rate, BACKUP_HOSPITALAR_100KW_ESPERADO.c_rate)

    def test_defaults_mais_conservadores(self):
        """Backup deve usar DoD=0.95 e reserva=0.20 por default."""
        r = dimensionar_backup(100.0, 4.0)
        assert r.premissas["dod"] == 0.95
        assert r.premissas["reserva_tecnica"] == 0.20

    def test_autonomia_8h_dobra_energia(self):
        r4 = dimensionar_backup(100.0, 4.0)
        r8 = dimensionar_backup(100.0, 8.0)
        assert _aprox(r8.energia_util_kwh, 2.0 * r4.energia_util_kwh)
        assert _aprox(r8.energia_nominal_kwh, 2.0 * r4.energia_nominal_kwh)
        # Potência permanece igual (mesma carga crítica)
        assert _aprox(r8.potencia_kw, r4.potencia_kw)


# ============================================================================
# Validações cruzadas entre os 3 casos
# ============================================================================


class TestComparacoesEntreCasos:
    """Sanity checks que valem para qualquer dimensionamento BESS."""

    def test_arbitragem_tem_c_rate_menor_que_peak_shaving(self):
        """ESS de longa duração (4h) é menos agressivo que peak shaving (2h)."""
        peak = dimensionar_arbitragem(1000.0, 4.0)
        shave_like = dimensionar_arbitragem(1000.0, 2.0)
        assert peak.c_rate < shave_like.c_rate

    def test_backup_consome_mais_dod_que_arbitragem(self):
        """DoD 0.95 (backup) > 0.90 (arbitragem) → banco menor por kWh útil."""
        e_util = 400.0
        backup = dimensionar_backup(100.0, 4.0)  # E_util=400, DoD=0.95
        # Mesma E_util mas com DoD=0.9 (arbitragem):
        arb = dimensionar_arbitragem(100.0, 4.0)  # E_util=400, DoD=0.90
        # Backup tem DoD maior MAS reserva maior também → preciso ver qual domina.
        # DoD: 0.95 vs 0.90 → backup precisa de 0.90/0.95 = 0.947× a capacidade
        # Reserva: 1.20 vs 1.10 → backup precisa de 1.20/1.10 = 1.091× a capacidade
        # Líquido: 0.947 × 1.091 = 1.033 → backup tem ~3 % mais kWh nominal
        razao = backup.energia_nominal_kwh / arb.energia_nominal_kwh
        assert _aprox(razao, (0.9 / 0.95) * (1.20 / 1.10))

    def test_todas_as_funcoes_retornam_premissas_auditaveis(self):
        ps = dimensionar_peak_shaving(
            [500.0] * 22 + [650.0, 650.0], 500.0, 23.50
        )
        ar = dimensionar_arbitragem(1000.0, 4.0)
        bk = dimensionar_backup(100.0, 4.0)
        for r in (ps, ar, bk):
            assert isinstance(r.premissas, dict)
            assert "dod" in r.premissas
            assert "eficiencia_rt" in r.premissas
            assert "reserva_tecnica" in r.premissas
            assert "eta_d_derivado" in r.premissas
