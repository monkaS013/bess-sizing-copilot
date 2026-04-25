"""
Testes do modulo bess_core.degradacao.

Cobre:
- Validacao de entrada.
- Propriedades fundamentais (SoH(0)=1, monotonicidade, soma calendarico+ciclico).
- Arrhenius (a cada +10C, k_cal aproximadamente dobra).
- Diferenciacao entre quimicas (LTO > LFP > NMC em vida util).
- Calibracao com Tier 1: LFP 25C 365 ciclos/ano deve dar EoL ~ 8 anos.
- Capacidade efetiva quando E_nominal fornecida.
- ciclos_ano como escalar OU como lista anual.
"""

from __future__ import annotations

import math

import pytest

from bess_core.degradacao import (
    ResultadoDegradacao,
    calcular_soh_anual,
)


TOL = 1e-9
TOL_REL = 0.02  # 2 % para comparacoes empiricas


# ===========================================================================
# Validacoes de entrada
# ===========================================================================


class TestValidacoes:

    def test_quimica_invalida(self):
        with pytest.raises(ValueError, match="quimica"):
            calcular_soh_anual("LiPo")  # type: ignore[arg-type]

    def test_dod_zero(self):
        with pytest.raises(ValueError):
            calcular_soh_anual("LFP", dod_medio=0.0)

    def test_dod_acima_de_1(self):
        with pytest.raises(ValueError):
            calcular_soh_anual("LFP", dod_medio=1.5)

    def test_temperatura_extrema_baixa(self):
        with pytest.raises(ValueError):
            calcular_soh_anual("LFP", temperatura_celsius=-50.0)

    def test_temperatura_extrema_alta(self):
        with pytest.raises(ValueError):
            calcular_soh_anual("LFP", temperatura_celsius=100.0)

    def test_horizonte_zero(self):
        with pytest.raises(ValueError):
            calcular_soh_anual("LFP", horizonte_anos=0)

    def test_ciclos_negativos(self):
        with pytest.raises(ValueError):
            calcular_soh_anual("LFP", ciclos_ano=-10)

    def test_ciclos_lista_tamanho_errado(self):
        with pytest.raises(ValueError, match="elementos"):
            calcular_soh_anual(
                "LFP", ciclos_ano=[300, 300, 300], horizonte_anos=20,
            )

    def test_energia_nominal_negativa(self):
        with pytest.raises(ValueError):
            calcular_soh_anual("LFP", energia_nominal_kwh=-100)

    def test_taxas_override_negativas(self):
        with pytest.raises(ValueError):
            calcular_soh_anual("LFP", k_cal_ref_override=-0.01)


# ===========================================================================
# Propriedades fundamentais
# ===========================================================================


class TestPropriedadesFundamentais:

    def test_soh_inicial_eh_1(self):
        r = calcular_soh_anual("LFP")
        assert r.soh_anual[0] == 1.0
        assert r.perda_calendarica_anual[0] == 0.0
        assert r.perda_ciclica_anual[0] == 0.0

    def test_soh_eh_monotonicamente_decrescente(self):
        r = calcular_soh_anual("LFP", ciclos_ano=300, horizonte_anos=20)
        for i in range(1, len(r.soh_anual)):
            assert r.soh_anual[i] <= r.soh_anual[i - 1] + TOL

    def test_soh_nunca_negativo(self):
        # Cenario extremo para forcar SoH a chegar a zero.
        r = calcular_soh_anual(
            "NMC", temperatura_celsius=60, ciclos_ano=2000,
            horizonte_anos=20,
        )
        for s in r.soh_anual:
            assert s >= 0.0

    def test_soma_perdas_eh_complemento_do_soh(self):
        """SoH(t) = 1 - perda_cal(t) - perda_cyc(t) (clipado em 0)."""
        r = calcular_soh_anual("LFP", ciclos_ano=300, horizonte_anos=15)
        for i in range(len(r.soh_anual)):
            esperado = max(
                0.0,
                1.0 - r.perda_calendarica_anual[i] - r.perda_ciclica_anual[i]
            )
            assert abs(r.soh_anual[i] - esperado) < TOL

    def test_horizonte_define_tamanho_de_listas(self):
        for h in [1, 5, 10, 20]:
            r = calcular_soh_anual("LFP", horizonte_anos=h)
            assert len(r.soh_anual) == h + 1
            assert len(r.perda_calendarica_anual) == h + 1
            assert len(r.perda_ciclica_anual) == h + 1

    def test_resultado_eh_imutavel(self):
        r = calcular_soh_anual("LFP")
        assert isinstance(r, ResultadoDegradacao)
        with pytest.raises(Exception):
            r.eol_anos = 0.0  # type: ignore[misc]

    def test_zero_ciclos_so_tem_calendarico(self):
        """Banco em standby: degradacao puramente calendarica."""
        r = calcular_soh_anual("LFP", ciclos_ano=0, horizonte_anos=10)
        for i in range(len(r.soh_anual)):
            assert r.perda_ciclica_anual[i] == 0.0

    def test_temperatura_baixa_diminui_calendarico(self):
        """A 15C, k_cal_eff < a 25C."""
        r25 = calcular_soh_anual("LFP", temperatura_celsius=25.0, ciclos_ano=0)
        r15 = calcular_soh_anual("LFP", temperatura_celsius=15.0, ciclos_ano=0)
        assert r15.k_cal_eff < r25.k_cal_eff
        assert r15.soh_anual[10] > r25.soh_anual[10]


# ===========================================================================
# Arrhenius
# ===========================================================================


class TestArrhenius:

    def test_fator_arrhenius_eh_1_a_25c(self):
        """A 25 C (referencia), fator deve ser exatamente 1."""
        r = calcular_soh_anual("LFP", temperatura_celsius=25.0)
        assert abs(r.premissas["fator_arrhenius"] - 1.0) < TOL

    def test_a_cada_10c_arrhenius_dobra(self):
        """Para Ea ~ 60 kJ/mol, +10 C deve dobrar k_cal aproximadamente."""
        r25 = calcular_soh_anual("LFP", temperatura_celsius=25.0)
        r35 = calcular_soh_anual("LFP", temperatura_celsius=35.0)
        razao = r35.k_cal_eff / r25.k_cal_eff
        # Espera-se entre 1.5 e 2.5 (regra de pollegar Arrhenius).
        assert 1.5 <= razao <= 2.5

    def test_temperatura_alta_acelera_calendarico(self):
        r25 = calcular_soh_anual("LFP", temperatura_celsius=25.0)
        r45 = calcular_soh_anual("LFP", temperatura_celsius=45.0)
        # k_cal_eff a 45 C deve ser ~4x a 25 C.
        assert r45.k_cal_eff > r25.k_cal_eff * 3.0


# ===========================================================================
# DoD scaling
# ===========================================================================


class TestDoDScaling:

    def test_dod_referencia_nao_altera_kcyc(self):
        """DoD = 0.80 (referencia) deve dar k_cyc_eff = k_cyc_ref."""
        r = calcular_soh_anual("LFP", dod_medio=0.80)
        assert abs(r.k_cyc_eff - 0.000033) < 1e-7

    def test_dod_maior_acelera_ciclico(self):
        r80 = calcular_soh_anual("LFP", dod_medio=0.80)
        r100 = calcular_soh_anual("LFP", dod_medio=1.00)
        assert r100.k_cyc_eff > r80.k_cyc_eff


# ===========================================================================
# Calibracao Tier 1 (LFP)
# ===========================================================================


class TestCalibracaoTier1:
    """
    Verifica que os defaults LFP geram EoL coerente com fichas tecnicas
    Huawei LUNA2000 / CATL EnerOne (~ 8-10 anos a 365 ciclos/ano, 25 C).
    """

    def test_eol_lfp_padrao(self):
        r = calcular_soh_anual(
            "LFP", temperatura_celsius=25.0, ciclos_ano=365, dod_medio=0.80,
        )
        assert r.eol_anos is not None
        assert 7.0 <= r.eol_anos <= 10.0  # janela coerente com Tier 1

    def test_lto_dura_mais_que_lfp(self):
        r_lfp = calcular_soh_anual("LFP", ciclos_ano=365)
        r_lto = calcular_soh_anual("LTO", ciclos_ano=365)
        # LTO eh notoriamente o mais durador; nao atinge EoL em 20 anos.
        assert r_lto.soh_anual[20] > r_lfp.soh_anual[20]

    def test_nmc_degrada_mais_que_lfp(self):
        r_lfp = calcular_soh_anual("LFP", ciclos_ano=365)
        r_nmc = calcular_soh_anual("NMC", ciclos_ano=365)
        assert r_nmc.soh_anual[10] < r_lfp.soh_anual[10]


# ===========================================================================
# ciclos_ano como lista
# ===========================================================================


class TestCiclosLista:

    def test_lista_constante_eh_equivalente_a_escalar(self):
        r_escalar = calcular_soh_anual("LFP", ciclos_ano=300, horizonte_anos=10)
        r_lista = calcular_soh_anual(
            "LFP", ciclos_ano=[300] * 10, horizonte_anos=10,
        )
        for i in range(len(r_escalar.soh_anual)):
            assert abs(r_escalar.soh_anual[i] - r_lista.soh_anual[i]) < TOL

    def test_lista_decrescente_diminui_perda_ciclica_total(self):
        """Mais ciclos cedo + menos depois ⇒ perda total maior cedo."""
        ciclos_const = [365] * 10
        ciclos_decresc = [500, 500, 500, 365, 365, 300, 300, 200, 200, 100]
        r_const = calcular_soh_anual(
            "LFP", ciclos_ano=ciclos_const, horizonte_anos=10,
        )
        r_dec = calcular_soh_anual(
            "LFP", ciclos_ano=ciclos_decresc, horizonte_anos=10,
        )
        # Soma de ciclos:
        # const: 3650; decresc: 3330. Mesmo k_cyc, total menor → menos perda.
        assert r_const.soh_anual[10] < r_dec.soh_anual[10]


# ===========================================================================
# Capacidade efetiva
# ===========================================================================


class TestCapacidadeEfetiva:

    def test_sem_e_nominal_capacidade_eh_none(self):
        r = calcular_soh_anual("LFP")
        assert r.capacidade_efetiva_anual_kwh is None

    def test_com_e_nominal_capacidade_eh_lista(self):
        r = calcular_soh_anual(
            "LFP", energia_nominal_kwh=400.0, horizonte_anos=10,
        )
        assert r.capacidade_efetiva_anual_kwh is not None
        assert len(r.capacidade_efetiva_anual_kwh) == 11
        # Ano 0: capacidade nominal cheia.
        assert r.capacidade_efetiva_anual_kwh[0] == 400.0
        # Ano 10: capacidade nominal x SoH ano 10.
        esperado = 400.0 * r.soh_anual[10]
        assert abs(r.capacidade_efetiva_anual_kwh[10] - esperado) < TOL


# ===========================================================================
# EoL
# ===========================================================================


class TestEoL:

    def test_eol_none_quando_nao_atinge(self):
        """Cenario muito gentil: LTO frio, poucos ciclos."""
        r = calcular_soh_anual(
            "LTO", temperatura_celsius=15.0, ciclos_ano=100,
            horizonte_anos=10,
        )
        assert r.eol_anos is None

    def test_eol_eh_interpolado_entre_anos(self):
        """EoL nao deve ser inteiro (interpolacao linear)."""
        r = calcular_soh_anual("LFP")
        if r.eol_anos is not None:
            # Esperado: EoL em algum lugar com fracao decimal.
            assert r.eol_anos != int(r.eol_anos)


# ===========================================================================
# Premissas
# ===========================================================================


class TestPremissas:

    def test_premissas_completas(self):
        r = calcular_soh_anual(
            "LFP", dod_medio=0.85, ciclos_ano=400,
            temperatura_celsius=30.0, horizonte_anos=15,
        )
        p = r.premissas
        assert p["quimica"] == "LFP"
        assert p["dod_medio"] == 0.85
        assert p["temperatura_celsius"] == 30.0
        assert p["horizonte_anos"] == 15
        assert p["ciclos_ano_total"] == 400 * 15
        assert "fator_arrhenius" in p
