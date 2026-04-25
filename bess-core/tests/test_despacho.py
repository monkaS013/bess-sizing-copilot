"""
Testes do modulo bess_core.despacho.

Cobre:
- Validacao de entrada (12 testes).
- Peak shaving: corte do excedente, SoC respeita bounds, recarga off-peak.
- Arbitragem: carrega em precos baixos, descarrega em altos, sensibilidade
  aos percentis.
- Autoconsumo hibrido: prioriza FV, banco preenche deficit.
- Conservacao de energia: E_in - E_out = perdas + delta_soc * E_nom.
- Limites fisicos: |p_carga|, |p_descarga| <= P_nom; SoC nunca foge de
  [soc_min, soc_max].
"""

from __future__ import annotations

import math

import pytest

from bess_core.despacho import (
    ResultadoDespacho,
    simular_despacho_horario,
)


TOL = 1e-6  # tolerancia numerica para invariantes
TOL_ENERGIA = 1e-3  # tolerancia para conservacao de energia (kWh)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def perfil_dia_industrial() -> list[float]:
    """Indústria 24h: base 500 kW, pico 650 kW (14-16h), noite 300 kW (0-6h)."""
    perfil = [500.0] * 24
    for h in range(0, 6):
        perfil[h] = 300.0
    perfil[14] = perfil[15] = 650.0
    return perfil


@pytest.fixture
def perfil_dia_fv() -> list[float]:
    """Curva FV típica: gera entre 7h e 18h, pico ao meio-dia."""
    fv: list[float] = []
    for h in range(24):
        if 7 <= h <= 18:
            # Curva senoidal grosseira, pico = 100 kW ao meio-dia
            fase = (h - 12) / 6 * (math.pi / 2)
            fv.append(100.0 * math.cos(fase))
        else:
            fv.append(0.0)
    return fv


@pytest.fixture
def precos_pld_24h() -> list[float]:
    """Preços PLD típicos: barato à noite, caro no horário de ponta."""
    precos = [200.0] * 24  # base
    for h in range(0, 6):
        precos[h] = 80.0     # madrugada barata
    for h in range(18, 22):
        precos[h] = 600.0    # ponta cara
    return precos


# ===========================================================================
# Validacao de entrada
# ===========================================================================


class TestValidacaoEntrada:

    def test_perfil_vazio(self):
        with pytest.raises(ValueError, match="vazio"):
            simular_despacho_horario(
                [], 100.0, 50.0, "peak_shaving", threshold_kw=500.0
            )

    def test_capacidade_zero(self):
        with pytest.raises(ValueError):
            simular_despacho_horario(
                [500.0] * 24, 0.0, 50.0, "peak_shaving", threshold_kw=500.0
            )

    def test_potencia_negativa(self):
        with pytest.raises(ValueError):
            simular_despacho_horario(
                [500.0] * 24, 100.0, -50.0, "peak_shaving",
                threshold_kw=500.0,
            )

    def test_dod_invalido(self):
        with pytest.raises(ValueError):
            simular_despacho_horario(
                [500.0] * 24, 100.0, 50.0, "peak_shaving",
                threshold_kw=500.0, dod=1.5,
            )

    def test_eficiencia_invalida(self):
        with pytest.raises(ValueError):
            simular_despacho_horario(
                [500.0] * 24, 100.0, 50.0, "peak_shaving",
                threshold_kw=500.0, eficiencia_rt=2.0,
            )

    def test_delta_t_zero(self):
        with pytest.raises(ValueError):
            simular_despacho_horario(
                [500.0] * 24, 100.0, 50.0, "peak_shaving",
                threshold_kw=500.0, delta_t_h=0.0,
            )

    def test_soc_inicial_fora_bounds(self):
        with pytest.raises(ValueError, match="soc_inicial"):
            simular_despacho_horario(
                [500.0] * 24, 100.0, 50.0, "peak_shaving",
                threshold_kw=500.0, soc_inicial=1.2,
            )

    def test_peak_shaving_sem_threshold(self):
        with pytest.raises(ValueError, match="threshold_kw"):
            simular_despacho_horario(
                [500.0] * 24, 100.0, 50.0, "peak_shaving"
            )

    def test_arbitragem_sem_tarifa(self):
        with pytest.raises(ValueError, match="tarifa"):
            simular_despacho_horario(
                [500.0] * 24, 100.0, 50.0, "arbitragem"
            )

    def test_arbitragem_tarifa_tamanho_errado(self):
        with pytest.raises(ValueError, match="comprimento"):
            simular_despacho_horario(
                [500.0] * 24, 100.0, 50.0, "arbitragem",
                tarifa_horaria_brl_kwh=[100.0] * 12,
            )

    def test_autoconsumo_sem_fv(self):
        with pytest.raises(ValueError, match="perfil_fv"):
            simular_despacho_horario(
                [500.0] * 24, 100.0, 50.0, "autoconsumo_hibrido"
            )

    def test_estrategia_desconhecida(self):
        with pytest.raises(ValueError, match="nao suportada"):
            simular_despacho_horario(
                [500.0] * 24, 100.0, 50.0, "magia_negra",
            )


# ===========================================================================
# Invariantes globais (qualquer estrategia)
# ===========================================================================


class TestInvariantesGlobais:
    """Propriedades que valem para QUALQUER simulacao consistente."""

    def test_soc_nunca_foge_dos_bounds_peak_shaving(self, perfil_dia_industrial):
        r = simular_despacho_horario(
            perfil_dia_industrial, 400.0, 200.0,
            "peak_shaving", threshold_kw=500.0, soc_inicial=0.5, dod=0.9,
        )
        soc_min = 1.0 - 0.9
        for s in r.soc:
            assert soc_min - TOL <= s <= 1.0 + TOL

    def test_p_carga_e_p_descarga_nao_excedem_p_nom(self, perfil_dia_industrial):
        r = simular_despacho_horario(
            perfil_dia_industrial, 400.0, 200.0,
            "peak_shaving", threshold_kw=500.0, soc_inicial=0.9,
        )
        for p_c in r.p_carga_kw:
            assert -TOL <= p_c <= 200.0 + TOL
        for p_d in r.p_descarga_kw:
            assert -TOL <= p_d <= 200.0 + TOL

    def test_carga_e_descarga_mutuamente_exclusivas(self, perfil_dia_industrial):
        r = simular_despacho_horario(
            perfil_dia_industrial, 400.0, 200.0,
            "peak_shaving", threshold_kw=500.0, soc_inicial=0.9,
        )
        for p_c, p_d in zip(r.p_carga_kw, r.p_descarga_kw):
            # Pelo menos um e zero (ou ambos)
            assert p_c == 0.0 or p_d == 0.0

    def test_conservacao_de_energia(self, perfil_dia_industrial):
        """E_in - E_out = perdas + ΔSoC × E_nominal."""
        r = simular_despacho_horario(
            perfil_dia_industrial, 400.0, 200.0,
            "peak_shaving", threshold_kw=500.0, soc_inicial=0.5,
        )
        e_residual = r.delta_soc * 400.0  # DC
        # Perdas equivalentes ja em AC (ver memorial).
        # Verificamos: E_carga - E_descarga = perdas + E_residual_AC
        # Onde E_residual_AC = E_residual_DC/eta_d quando descarga e
        # E_residual_AC = E_residual_DC/eta_c quando carga.
        # Aqui simplificamos com a identidade DC:
        # (E_carga * eta_c) - (E_descarga / eta_d) = ΔSoC × E_nom
        eta_c = math.sqrt(0.92)
        eta_d = math.sqrt(0.92)
        balanco_dc = (
            r.energia_carregada_kwh * eta_c
            - r.energia_descarregada_kwh / eta_d
        )
        assert abs(balanco_dc - r.delta_soc * 400.0) < TOL_ENERGIA

    def test_resultado_eh_dataclass_imutavel(self, perfil_dia_industrial):
        r = simular_despacho_horario(
            perfil_dia_industrial, 400.0, 200.0,
            "peak_shaving", threshold_kw=500.0,
        )
        assert isinstance(r, ResultadoDespacho)
        with pytest.raises(Exception):
            r.energia_carregada_kwh = 0.0  # type: ignore[misc]

    def test_soc_tem_n_mais_1_pontos(self, perfil_dia_industrial):
        r = simular_despacho_horario(
            perfil_dia_industrial, 400.0, 200.0,
            "peak_shaving", threshold_kw=500.0,
        )
        assert len(r.soc) == len(perfil_dia_industrial) + 1
        assert len(r.p_carga_kw) == len(perfil_dia_industrial)


# ===========================================================================
# Peak shaving
# ===========================================================================


class TestPeakShaving:

    def test_corte_exato_no_threshold(self, perfil_dia_industrial):
        """Com SoC suficiente, demanda apos BESS nunca excede threshold."""
        r = simular_despacho_horario(
            perfil_dia_industrial, 500.0, 250.0,
            "peak_shaving", threshold_kw=500.0, soc_inicial=0.95,
        )
        assert max(r.demanda_apos_bess_kw) <= 500.0 + TOL

    def test_descarga_concentrada_nas_horas_de_pico(self, perfil_dia_industrial):
        r = simular_despacho_horario(
            perfil_dia_industrial, 500.0, 250.0,
            "peak_shaving", threshold_kw=500.0, soc_inicial=0.95,
        )
        # Soma das descargas nas horas de pico (14h, 15h) = 300 kWh esperado.
        descarga_pico = r.p_descarga_kw[14] + r.p_descarga_kw[15]
        assert abs(descarga_pico * 1.0 - 300.0) < 1.0

    def test_recarga_nas_horas_off_peak(self, perfil_dia_industrial):
        """Madrugada (carga 300 kW < threshold 500) deve permitir recarga."""
        r = simular_despacho_horario(
            perfil_dia_industrial, 500.0, 250.0,
            "peak_shaving", threshold_kw=500.0, soc_inicial=0.2,
        )
        # Pelo menos uma hora da madrugada (0-6h) tem carga > 0.
        assert any(p_c > 0 for p_c in r.p_carga_kw[0:6])

    def test_sem_pico_sem_descarga(self):
        """Carga sempre abaixo do threshold ⇒ nenhuma descarga."""
        perfil = [400.0] * 24
        r = simular_despacho_horario(
            perfil, 200.0, 100.0,
            "peak_shaving", threshold_kw=500.0, soc_inicial=0.5,
        )
        assert sum(r.p_descarga_kw) == 0.0

    def test_soc_baixo_limita_descarga(self):
        """SoC inicial muito baixo ⇒ banco nao consegue cortar tudo."""
        perfil = [500.0] * 24
        perfil[14] = perfil[15] = 800.0  # pico de 300 kW * 2h = 600 kWh
        # Banco pequeno: 200 kWh nominal, SoC inicial baixo ⇒ insuficiente.
        r = simular_despacho_horario(
            perfil, 200.0, 200.0,
            "peak_shaving", threshold_kw=500.0,
            soc_inicial=0.5,  # so 100 kWh DC disponivel
        )
        # Vai ter horas de pico onde a demanda excede 500.
        assert max(r.demanda_apos_bess_kw) > 500.0

    def test_p_grid_corresponde_ao_corte(self, perfil_dia_industrial):
        """p_grid no horario de pico deve cair quando ha descarga."""
        r = simular_despacho_horario(
            perfil_dia_industrial, 500.0, 250.0,
            "peak_shaving", threshold_kw=500.0, soc_inicial=0.95,
        )
        # Hora 14: carga=650, descarga deve ser 150, p_grid=500.
        assert abs(r.p_grid_kw[14] - 500.0) < TOL


# ===========================================================================
# Arbitragem
# ===========================================================================


class TestArbitragem:

    def test_carrega_apenas_em_precos_baixos(self, precos_pld_24h):
        perfil = [100.0] * 24  # carga constante
        r = simular_despacho_horario(
            perfil, 400.0, 100.0,
            "arbitragem", tarifa_horaria_brl_kwh=precos_pld_24h,
            soc_inicial=0.5,
        )
        # Carga so deve ocorrer em horas com preco <= percentil 25%.
        p_carga_thresh = r.premissas["percentil_carga_brl"]
        for t in range(24):
            if r.p_carga_kw[t] > 0:
                assert precos_pld_24h[t] <= p_carga_thresh + TOL

    def test_descarrega_apenas_em_precos_altos(self, precos_pld_24h):
        perfil = [100.0] * 24
        r = simular_despacho_horario(
            perfil, 400.0, 100.0,
            "arbitragem", tarifa_horaria_brl_kwh=precos_pld_24h,
            soc_inicial=0.5,
        )
        p_desc_thresh = r.premissas["percentil_descarga_brl"]
        for t in range(24):
            if r.p_descarga_kw[t] > 0:
                assert precos_pld_24h[t] >= p_desc_thresh - TOL

    def test_throughput_compativel_com_um_ciclo_dia(self, precos_pld_24h):
        """Em 24h com PLD bem distribuido, espera-se ~1 ciclo."""
        perfil = [100.0] * 24
        r = simular_despacho_horario(
            perfil, 400.0, 100.0,
            "arbitragem", tarifa_horaria_brl_kwh=precos_pld_24h,
            soc_inicial=0.5,
        )
        # Espera-se algo entre 0.5 e 1.5 ciclos (banco com 4h de duracao,
        # 4h baratas + 4h caras no dia).
        assert 0.3 <= r.ciclos_equivalentes <= 1.5


# ===========================================================================
# Autoconsumo hibrido
# ===========================================================================


class TestAutoconsumoHibrido:

    def test_carrega_quando_fv_excede_carga(self, perfil_dia_fv):
        """Carga 50 kW; FV até 100 kW ao meio-dia ⇒ banco carrega."""
        perfil = [50.0] * 24
        r = simular_despacho_horario(
            perfil, 400.0, 100.0,
            "autoconsumo_hibrido", perfil_fv_kw=perfil_dia_fv,
            soc_inicial=0.2,
        )
        # No meio-dia FV pico (~100 kW) > carga (50 kW) ⇒ p_carga > 0.
        assert r.p_carga_kw[12] > 0.0

    def test_descarrega_quando_fv_insuficiente(self, perfil_dia_fv):
        """Carga 200 kW; FV insuficiente ⇒ banco descarrega."""
        perfil = [200.0] * 24
        r = simular_despacho_horario(
            perfil, 400.0, 100.0,
            "autoconsumo_hibrido", perfil_fv_kw=perfil_dia_fv,
            soc_inicial=0.9,
        )
        # Madrugada: FV=0, carga=200 ⇒ banco deveria descarregar.
        assert any(p_d > 0 for p_d in r.p_descarga_kw[0:6])

    def test_sem_fv_nao_carrega(self):
        """FV identicamente zero ⇒ banco nunca carrega."""
        perfil = [300.0] * 24
        fv_zero = [0.0] * 24
        r = simular_despacho_horario(
            perfil, 400.0, 100.0,
            "autoconsumo_hibrido", perfil_fv_kw=fv_zero,
            soc_inicial=0.9,
        )
        assert sum(r.p_carga_kw) == 0.0

    def test_p_grid_negativo_em_excedente_fv(self):
        """FV >> carga + capacidade do banco ⇒ exporta para rede."""
        perfil = [10.0] * 24
        fv_alto = [200.0] * 24  # excedente massivo
        r = simular_despacho_horario(
            perfil, 100.0, 50.0,
            "autoconsumo_hibrido", perfil_fv_kw=fv_alto,
            soc_inicial=0.9,  # banco quase cheio
        )
        # Ha excedente ⇒ p_grid negativo (export) em alguma hora.
        assert any(g < 0 for g in r.p_grid_kw)
        assert r.energia_grid_exportada_kwh > 0


# ===========================================================================
# Premissas / metadados
# ===========================================================================


class TestPremissasAuditoria:

    def test_premissas_tem_estrategia(self, perfil_dia_industrial):
        r = simular_despacho_horario(
            perfil_dia_industrial, 400.0, 200.0,
            "peak_shaving", threshold_kw=500.0,
        )
        assert r.premissas["estrategia"] == "peak_shaving"
        assert r.premissas["horizonte_passos"] == 24
        assert r.premissas["horizonte_horas"] == 24.0

    def test_premissas_eta_c_eta_d_simetricos(self, perfil_dia_industrial):
        r = simular_despacho_horario(
            perfil_dia_industrial, 400.0, 200.0,
            "peak_shaving", threshold_kw=500.0, eficiencia_rt=0.92,
        )
        assert math.isclose(r.premissas["eta_c"], math.sqrt(0.92))
        assert math.isclose(r.premissas["eta_d"], math.sqrt(0.92))

    def test_premissas_arbitragem_tem_percentis(self, precos_pld_24h):
        r = simular_despacho_horario(
            [100.0] * 24, 400.0, 100.0,
            "arbitragem", tarifa_horaria_brl_kwh=precos_pld_24h,
        )
        assert r.premissas["percentil_carga"] == 0.25
        assert r.premissas["percentil_descarga"] == 0.75
        assert r.premissas["percentil_carga_brl"] is not None
