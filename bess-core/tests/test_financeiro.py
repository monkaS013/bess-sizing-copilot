"""
Testes do modulo bess_core.financeiro.

Cobre:
- Identidades matematicas (VPL@TIR=0; VPL@wacc=0 = soma nominal; payback
  simples = CAPEX/(eco-opex) sem degradacao/inflacao).
- Validacao de entrada.
- Edge cases (economia zero, projeto inviavel).
- Sensibilidade tornado (4 variaveis).
- LCOS e fluxos de caixa.
"""

from __future__ import annotations

import pytest

from bess_core.financeiro import (
    AnaliseFinanceira,
    SensibilidadeItem,
    analisar_financeiro,
)


TOL_BRL = 1.0       # tolerancia de R$ 1
TOL_PCT = 0.01      # tolerancia de 0.01 % (TIR)


# ===========================================================================
# Validacoes de entrada
# ===========================================================================


class TestValidacoes:

    def test_capex_zero(self):
        with pytest.raises(ValueError):
            analisar_financeiro(0.0, 10_000, 100_000, 50_000)

    def test_capex_negativo(self):
        with pytest.raises(ValueError):
            analisar_financeiro(-100.0, 10_000, 100_000, 50_000)

    def test_opex_negativo(self):
        with pytest.raises(ValueError):
            analisar_financeiro(1_000_000, -10.0, 100_000, 50_000)

    def test_horizonte_zero(self):
        with pytest.raises(ValueError):
            analisar_financeiro(
                1_000_000, 10_000, 100_000, 50_000, horizonte_anos=0,
            )

    def test_wacc_invalido(self):
        with pytest.raises(ValueError):
            analisar_financeiro(
                1_000_000, 10_000, 100_000, 50_000, wacc=-1.5,
            )

    def test_degradacao_invalida(self):
        with pytest.raises(ValueError):
            analisar_financeiro(
                1_000_000, 10_000, 100_000, 50_000,
                degradacao_anual_economia=1.5,
            )

    def test_inflacao_invalida(self):
        with pytest.raises(ValueError):
            analisar_financeiro(
                1_000_000, 10_000, 100_000, 50_000,
                inflacao_opex=2.0,
            )

    def test_valor_residual_negativo(self):
        with pytest.raises(ValueError):
            analisar_financeiro(
                1_000_000, 10_000, 100_000, 50_000,
                valor_residual_brl=-100,
            )


# ===========================================================================
# Identidades matematicas
# ===========================================================================


class TestIdentidadesMatematicas:
    """Propriedades que devem valer por construcao."""

    def test_vpl_em_taxa_zero_eh_soma_nominal(self):
        """Com WACC=0, VPL = soma simples dos fluxos."""
        r = analisar_financeiro(
            capex_brl=1_000_000,
            opex_anual_brl=0,
            economia_anual_brl=200_000,
            energia_descarregada_anual_kwh=50_000,
            horizonte_anos=10,
            wacc=0.0,
            degradacao_anual_economia=0.0,
            inflacao_opex=0.0,
        )
        # Esperado: -1M + 10 anos x 200k = -1M + 2M = +1M.
        assert abs(r.vpl_brl - 1_000_000) < TOL_BRL

    def test_vpl_na_tir_eh_zero(self):
        """VPL avaliado na TIR deve dar zero."""
        r = analisar_financeiro(
            capex_brl=1_500_000,
            opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
        )
        assert r.tir_percent is not None
        # Reconstruir e calcular VPL na TIR.
        from bess_core.financeiro import _vpl
        tir = r.tir_percent / 100.0
        vpl_na_tir = _vpl(r.fluxos_caixa_anuais_brl, tir)
        assert abs(vpl_na_tir) < TOL_BRL

    def test_payback_simples_sem_degradacao_eh_capex_dividido_cf(self):
        """Sem degradacao/inflacao: payback = CAPEX / (eco - opex)."""
        capex = 1_000_000
        eco = 200_000
        opex = 50_000
        r = analisar_financeiro(
            capex_brl=capex,
            opex_anual_brl=opex,
            economia_anual_brl=eco,
            energia_descarregada_anual_kwh=10_000,
            degradacao_anual_economia=0.0,
            inflacao_opex=0.0,
        )
        esperado = capex / (eco - opex)  # 6.6667 anos
        assert abs(r.payback_simples_anos - esperado) < 0.01

    def test_payback_descontado_maior_que_simples(self):
        """Para projeto viavel, payback descontado > payback simples."""
        r = analisar_financeiro(
            capex_brl=1_500_000,
            opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
        )
        assert r.payback_descontado_anos > r.payback_simples_anos

    def test_vpl_acumulado_eh_monotonico_apos_tornar_positivo(self):
        """Apos cruzamento de zero, VPL acumulado so cresce."""
        r = analisar_financeiro(
            capex_brl=1_500_000, opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
        )
        # Encontrar o primeiro ano com VPL >= 0 e checar monotonia dali em diante.
        positivos = [v for v in r.vpl_acumulado_brl if v >= 0]
        for i in range(1, len(positivos)):
            assert positivos[i] >= positivos[i - 1] - TOL_BRL

    def test_fluxos_caixa_tem_n_mais_1(self):
        r = analisar_financeiro(
            capex_brl=1_000_000, opex_anual_brl=10_000,
            economia_anual_brl=200_000,
            energia_descarregada_anual_kwh=50_000,
            horizonte_anos=15,
        )
        assert len(r.fluxos_caixa_anuais_brl) == 16
        assert r.fluxos_caixa_anuais_brl[0] == -1_000_000

    def test_lcos_positivo_e_finito(self):
        r = analisar_financeiro(
            capex_brl=1_500_000, opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
        )
        assert r.lcos_brl_mwh > 0
        assert r.lcos_brl_mwh < 1e6  # sanity

    def test_lcos_decai_com_mais_energia(self):
        """Mais kWh entregues por ano ⇒ LCOS menor (custo fixo diluido)."""
        kwargs = dict(
            capex_brl=1_500_000, opex_anual_brl=15_000,
            economia_anual_brl=350_000,
        )
        r_baixa = analisar_financeiro(
            **kwargs, energia_descarregada_anual_kwh=50_000,
        )
        r_alta = analisar_financeiro(
            **kwargs, energia_descarregada_anual_kwh=200_000,
        )
        assert r_alta.lcos_brl_mwh < r_baixa.lcos_brl_mwh


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:

    def test_economia_zero_payback_indefinido(self):
        """Sem economia, projeto nunca paga ⇒ payback = None."""
        r = analisar_financeiro(
            capex_brl=1_000_000, opex_anual_brl=0,
            economia_anual_brl=0,
            energia_descarregada_anual_kwh=0,
            incluir_sensibilidade=False,
        )
        assert r.payback_simples_anos is None
        assert r.payback_descontado_anos is None
        assert r.vpl_brl == -1_000_000

    def test_projeto_inviavel_tir_baixa(self):
        """Projeto que gera pouco ⇒ TIR < WACC ⇒ VPL < 0."""
        r = analisar_financeiro(
            capex_brl=10_000_000, opex_anual_brl=100_000,
            economia_anual_brl=300_000,  # nao paga em 20 anos
            energia_descarregada_anual_kwh=50_000,
        )
        assert r.vpl_brl < 0
        # TIR pode ser baixa ou indefinida.
        if r.tir_percent is not None:
            assert r.tir_percent < 12  # menor que WACC

    def test_horizonte_curto_payback_nao_atingido(self):
        """Horizonte 2 anos com payback teorico de 5 anos ⇒ None."""
        r = analisar_financeiro(
            capex_brl=1_000_000, opex_anual_brl=0,
            economia_anual_brl=200_000,
            energia_descarregada_anual_kwh=10_000,
            horizonte_anos=2,
            incluir_sensibilidade=False,
        )
        assert r.payback_simples_anos is None

    def test_valor_residual_aumenta_vpl(self):
        """VR > 0 ⇒ VPL maior."""
        kwargs = dict(
            capex_brl=1_500_000, opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
        )
        r0 = analisar_financeiro(**kwargs, valor_residual_brl=0)
        r1 = analisar_financeiro(**kwargs, valor_residual_brl=200_000)
        assert r1.vpl_brl > r0.vpl_brl

    def test_resultado_eh_imutavel(self):
        r = analisar_financeiro(
            capex_brl=1_000_000, opex_anual_brl=10_000,
            economia_anual_brl=200_000,
            energia_descarregada_anual_kwh=50_000,
        )
        assert isinstance(r, AnaliseFinanceira)
        with pytest.raises(Exception):
            r.vpl_brl = 0.0  # type: ignore[misc]


# ===========================================================================
# Sensibilidade
# ===========================================================================


class TestSensibilidade:

    def test_quatro_itens_no_tornado(self):
        r = analisar_financeiro(
            capex_brl=1_500_000, opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
        )
        nomes = {item.variavel for item in r.sensibilidade}
        assert nomes == {"CAPEX", "OPEX", "Economia", "WACC"}

    def test_capex_maior_reduz_vpl(self):
        r = analisar_financeiro(
            capex_brl=1_500_000, opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
        )
        item = next(i for i in r.sensibilidade if i.variavel == "CAPEX")
        # CAPEX +20% ⇒ VPL menor
        assert item.vpl_alto_brl < item.vpl_central_brl
        # CAPEX -20% ⇒ VPL maior
        assert item.vpl_baixo_brl > item.vpl_central_brl

    def test_economia_maior_aumenta_vpl(self):
        r = analisar_financeiro(
            capex_brl=1_500_000, opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
        )
        item = next(i for i in r.sensibilidade if i.variavel == "Economia")
        assert item.vpl_alto_brl > item.vpl_central_brl
        assert item.vpl_baixo_brl < item.vpl_central_brl

    def test_economia_eh_variavel_mais_sensivel(self):
        """Em projetos BESS BR, economia tipicamente domina o tornado."""
        r = analisar_financeiro(
            capex_brl=1_500_000, opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
        )
        ranges = {
            i.variavel: i.vpl_alto_brl - i.vpl_baixo_brl
            for i in r.sensibilidade
        }
        # Ordem esperada: economia > {capex, wacc} > opex.
        assert ranges["Economia"] > ranges["OPEX"]

    def test_sensibilidade_pode_ser_desativada(self):
        r = analisar_financeiro(
            capex_brl=1_000_000, opex_anual_brl=10_000,
            economia_anual_brl=200_000,
            energia_descarregada_anual_kwh=50_000,
            incluir_sensibilidade=False,
        )
        assert r.sensibilidade == []


# ===========================================================================
# Premissas
# ===========================================================================


class TestPremissas:

    def test_premissas_completas(self):
        r = analisar_financeiro(
            capex_brl=1_500_000, opex_anual_brl=15_000,
            economia_anual_brl=350_000,
            energia_descarregada_anual_kwh=110_000,
            horizonte_anos=15, wacc=0.10,
            degradacao_anual_economia=0.025,
            inflacao_opex=0.05, valor_residual_brl=50_000,
        )
        p = r.premissas
        assert p["horizonte_anos"] == 15
        assert p["wacc"] == 0.10
        assert p["degradacao_anual_economia"] == 0.025
        assert p["inflacao_opex"] == 0.05
        assert p["valor_residual_brl"] == 50_000
        assert p["energia_descarregada_anual_kwh"] == 110_000
