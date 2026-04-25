"""
Testes do módulo ``bess_core.dimensionamento``.

Caso de referência — Sprint 1.1
-------------------------------
Indústria com 500 kW de demanda contratada; pico de 650 kW por 2 h em 5 dias
úteis; finais de semana sem pico.

Cálculo manual esperado (planilha de validação)
-----------------------------------------------
P_shave        = 650 − 500                                = 150 kW
E_evento_max   = 150 kW × 2 h                             = 300 kWh
E_util         = 300 kWh
η_d            = √0.92                                    ≈ 0.9592
E_nominal      = 300 / (0.9 × 0.9592) × 1.10              ≈ 382.2 kWh
P_nominal      = 150 / 0.9592 × 1.10                      ≈ 172.0 kW
C-rate         = 172.0 / 382.2                            ≈ 0.450 C
N_eventos      = 5 (um por dia útil)

Tolerância adotada: 2 % (compatível com incerteza de fichas técnicas).
"""

import math

import pytest

from bess_core.dimensionamento import (
    DimensionamentoBESS,
    dimensionar_peak_shaving,
)


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

TOLERANCIA = 0.02  # 2 %


def aprox(obtido: float, esperado: float, tol: float = TOLERANCIA) -> bool:
    """Compara dois floats com tolerância relativa."""
    if esperado == 0:
        return abs(obtido) <= tol
    return abs(obtido - esperado) / abs(esperado) <= tol


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def perfil_industrial_semanal() -> list[float]:
    """
    Semana típica de uma indústria 500 kW:

    - Seg–Sex (5 dias): base 500 kW; pico de 650 kW das 14 h às 16 h.
    - Sáb–Dom: base 300 kW; sem picos.

    Total: 168 horas (7 dias).
    """
    perfil: list[float] = []
    for dia in range(7):
        if dia < 5:  # dias úteis
            base = [500.0] * 24
            base[14] = 650.0
            base[15] = 650.0
        else:        # fim de semana
            base = [300.0] * 24
        perfil.extend(base)
    return perfil


@pytest.fixture
def perfil_diario_simples() -> list[float]:
    """Dia único com um pico de 2 h."""
    perfil = [500.0] * 24
    perfil[14] = 650.0
    perfil[15] = 650.0
    return perfil


# ---------------------------------------------------------------------------
# Caso real — indústria 500 kW
# ---------------------------------------------------------------------------


class TestPeakShavingIndustrial500kW:
    """Validação numérica contra cálculo manual (planilha)."""

    def test_potencia_shave(self, perfil_industrial_semanal):
        r = dimensionar_peak_shaving(
            perfil_industrial_semanal,
            demanda_contratada_kw=500.0,
            tarifa_demanda_brl_kw=23.50,
        )
        assert aprox(r.p_shave_kw, 150.0)

    def test_energia_evento_max(self, perfil_industrial_semanal):
        r = dimensionar_peak_shaving(
            perfil_industrial_semanal, 500.0, 23.50
        )
        assert aprox(r.energia_evento_max_kwh, 300.0)

    def test_energia_util(self, perfil_industrial_semanal):
        r = dimensionar_peak_shaving(
            perfil_industrial_semanal, 500.0, 23.50
        )
        # Energia útil entregue à carga = pior evento (sem derating).
        assert aprox(r.energia_util_kwh, 300.0)

    def test_n_eventos_pico(self, perfil_industrial_semanal):
        r = dimensionar_peak_shaving(
            perfil_industrial_semanal, 500.0, 23.50
        )
        assert r.n_eventos_pico == 5

    def test_energia_nominal(self, perfil_industrial_semanal):
        r = dimensionar_peak_shaving(
            perfil_industrial_semanal, 500.0, 23.50
        )
        eta_d = math.sqrt(0.92)
        esperado = 300.0 / (0.9 * eta_d) * 1.10
        assert aprox(r.energia_nominal_kwh, esperado)
        # Sanity: ~382 kWh
        assert 375.0 <= r.energia_nominal_kwh <= 390.0

    def test_potencia_nominal(self, perfil_industrial_semanal):
        r = dimensionar_peak_shaving(
            perfil_industrial_semanal, 500.0, 23.50
        )
        eta_d = math.sqrt(0.92)
        esperado = 150.0 / eta_d * 1.10
        assert aprox(r.potencia_kw, esperado)
        # Sanity: ~172 kW
        assert 168.0 <= r.potencia_kw <= 175.0

    def test_c_rate(self, perfil_industrial_semanal):
        r = dimensionar_peak_shaving(
            perfil_industrial_semanal, 500.0, 23.50
        )
        # C ≈ 0.45 — banco de média potência, típico LFP comercial.
        assert 0.40 <= r.c_rate <= 0.50

    def test_premissas_para_auditoria(self, perfil_industrial_semanal):
        r = dimensionar_peak_shaving(
            perfil_industrial_semanal, 500.0, 23.50
        )
        p = r.premissas
        assert p["demanda_contratada_kw"] == 500.0
        assert p["tarifa_demanda_brl_kw"] == 23.50
        assert p["dod"] == 0.9
        assert p["eficiencia_rt"] == 0.92
        assert p["reserva_tecnica"] == 0.1
        assert p["delta_t_h"] == 1.0
        assert p["horas_amostradas"] == 168
        assert math.isclose(p["eta_d_derivado"], math.sqrt(0.92))

    def test_retorno_eh_dataclass_imutavel(self, perfil_industrial_semanal):
        r = dimensionar_peak_shaving(
            perfil_industrial_semanal, 500.0, 23.50
        )
        assert isinstance(r, DimensionamentoBESS)
        with pytest.raises(Exception):
            # frozen dataclass → atribuição deve falhar
            r.energia_util_kwh = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Variantes do caso base
# ---------------------------------------------------------------------------


class TestVariantes:

    def test_perfil_diario_um_evento(self, perfil_diario_simples):
        r = dimensionar_peak_shaving(perfil_diario_simples, 500.0, 23.50)
        assert r.n_eventos_pico == 1
        assert aprox(r.p_shave_kw, 150.0)
        assert aprox(r.energia_evento_max_kwh, 300.0)

    def test_dois_eventos_no_mesmo_dia(self):
        # Dois picos separados por um vale — devem contar como 2 eventos.
        perfil = [500.0] * 24
        perfil[10] = 600.0  # evento 1: 100 kW × 1 h = 100 kWh
        perfil[14] = 650.0  # evento 2: 150 kW × 2 h = 300 kWh
        perfil[15] = 650.0
        r = dimensionar_peak_shaving(perfil, 500.0, 23.50)
        assert r.n_eventos_pico == 2
        # Pior evento = 300 kWh (o segundo); P_shave = 150 kW.
        assert aprox(r.energia_evento_max_kwh, 300.0)
        assert aprox(r.p_shave_kw, 150.0)

    def test_evento_no_final_do_perfil(self):
        # Evento aberto no último passo deve ser fechado corretamente.
        perfil = [500.0] * 22 + [650.0, 650.0]
        r = dimensionar_peak_shaving(perfil, 500.0, 23.50)
        assert r.n_eventos_pico == 1
        assert aprox(r.energia_evento_max_kwh, 300.0)

    def test_delta_t_15min(self):
        # 96 amostras de 15 min = 24 h. Pico de 150 kW por 8 amostras (2 h).
        perfil = [500.0] * 96
        for i in range(56, 64):  # 14:00–16:00 em passos de 15 min
            perfil[i] = 650.0
        r = dimensionar_peak_shaving(
            perfil, 500.0, 23.50, delta_t_h=0.25
        )
        # 8 × 0.25 h × 150 kW = 300 kWh
        assert aprox(r.energia_evento_max_kwh, 300.0)
        assert aprox(r.p_shave_kw, 150.0)

    def test_efeito_da_reserva_tecnica(self, perfil_diario_simples):
        r0 = dimensionar_peak_shaving(
            perfil_diario_simples, 500.0, 23.50, reserva_tecnica=0.0
        )
        r1 = dimensionar_peak_shaving(
            perfil_diario_simples, 500.0, 23.50, reserva_tecnica=0.20
        )
        # Reserva 20 % → energia nominal e potência 20 % maiores.
        assert aprox(r1.energia_nominal_kwh, r0.energia_nominal_kwh * 1.20)
        assert aprox(r1.potencia_kw, r0.potencia_kw * 1.20)
        # C-rate é invariante (ambos escalam pelo mesmo fator).
        assert aprox(r1.c_rate, r0.c_rate)

    def test_dod_menor_aumenta_banco(self, perfil_diario_simples):
        r_lfp = dimensionar_peak_shaving(
            perfil_diario_simples, 500.0, 23.50, dod=0.9
        )
        r_chumbo = dimensionar_peak_shaving(
            perfil_diario_simples, 500.0, 23.50, dod=0.5
        )
        # Bateria de chumbo (DoD 50 %) precisa ser ~1.8× maior em kWh.
        assert r_chumbo.energia_nominal_kwh > r_lfp.energia_nominal_kwh
        razao = r_chumbo.energia_nominal_kwh / r_lfp.energia_nominal_kwh
        assert aprox(razao, 0.9 / 0.5)


# ---------------------------------------------------------------------------
# Validações de entrada
# ---------------------------------------------------------------------------


class TestValidacoesEntrada:

    def test_perfil_vazio(self):
        with pytest.raises(ValueError, match="vazio"):
            dimensionar_peak_shaving([], 500.0, 23.50)

    def test_demanda_zero(self):
        with pytest.raises(ValueError):
            dimensionar_peak_shaving([100.0] * 24, 0.0, 23.50)

    def test_demanda_negativa(self):
        with pytest.raises(ValueError):
            dimensionar_peak_shaving([100.0] * 24, -500.0, 23.50)

    def test_dod_acima_de_1(self):
        with pytest.raises(ValueError):
            dimensionar_peak_shaving([700.0] * 24, 500.0, 23.50, dod=1.5)

    def test_dod_zero(self):
        with pytest.raises(ValueError):
            dimensionar_peak_shaving([700.0] * 24, 500.0, 23.50, dod=0.0)

    def test_eficiencia_acima_de_1(self):
        with pytest.raises(ValueError):
            dimensionar_peak_shaving(
                [700.0] * 24, 500.0, 23.50, eficiencia_rt=1.2
            )

    def test_reserva_negativa(self):
        with pytest.raises(ValueError):
            dimensionar_peak_shaving(
                [700.0] * 24, 500.0, 23.50, reserva_tecnica=-0.1
            )

    def test_delta_t_zero(self):
        with pytest.raises(ValueError):
            dimensionar_peak_shaving(
                [700.0] * 24, 500.0, 23.50, delta_t_h=0.0
            )

    def test_perfil_negativo(self):
        with pytest.raises(ValueError, match="negativ"):
            dimensionar_peak_shaving([-10.0] * 24, 500.0, 23.50)

    def test_carga_sempre_abaixo_da_contratada(self):
        with pytest.raises(ValueError, match="desnecess"):
            dimensionar_peak_shaving([400.0] * 24, 500.0, 23.50)
