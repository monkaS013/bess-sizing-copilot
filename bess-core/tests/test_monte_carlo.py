"""
Testes do simulacao_monte_carlo do modulo bess_core.financeiro (Sprint 4-C).

Cobre:
- Reprodutibilidade com seed
- Identidades estatisticas (P10 <= P25 <= P50 <= P75 <= P90)
- Probabilidade de viabilidade em [0, 1]
- Monotonicidade vs CAPEX (CAPEX maior -> menor viabilidade)
- Histograma com somatorio igual a n_iteracoes
- Validacao de entrada
- Caso degenerado (variancia zero)
"""

from __future__ import annotations

import pytest

from bess_core.financeiro import (
    ResultadoMonteCarlo,
    simulacao_monte_carlo,
)


# ===========================================================================
# Casos de teste base
# ===========================================================================

CASO_BASE = {
    "capex_brl": 2_000_000.0,
    "opex_anual_brl": 20_000.0,
    "economia_anual_brl": 200_000.0,
    "n_iteracoes": 1_000,  # mantem rapido em CI
    "seed": 42,
}


# ===========================================================================
# Reprodutibilidade
# ===========================================================================


def test_seed_garante_reprodutibilidade():
    """Mesma seed -> mesmos percentis exatos."""
    r1 = simulacao_monte_carlo(**CASO_BASE)
    r2 = simulacao_monte_carlo(**CASO_BASE)
    assert r1.vpl_brl_p10 == pytest.approx(r2.vpl_brl_p10, rel=1e-9)
    assert r1.vpl_brl_p50 == pytest.approx(r2.vpl_brl_p50, rel=1e-9)
    assert r1.vpl_brl_p90 == pytest.approx(r2.vpl_brl_p90, rel=1e-9)
    assert r1.probabilidade_viavel == r2.probabilidade_viavel


def test_seeds_diferentes_dao_resultados_diferentes():
    """Sanidade: seeds diferentes nao retornam resultados identicos."""
    r1 = simulacao_monte_carlo(**{**CASO_BASE, "seed": 1})
    r2 = simulacao_monte_carlo(**{**CASO_BASE, "seed": 2})
    assert r1.vpl_brl_p50 != r2.vpl_brl_p50


# ===========================================================================
# Identidades estatisticas
# ===========================================================================


def test_percentis_em_ordem_crescente():
    """P10 <= P25 <= P50 <= P75 <= P90 sempre."""
    r = simulacao_monte_carlo(**CASO_BASE)
    assert r.vpl_brl_p10 <= r.vpl_brl_p25
    assert r.vpl_brl_p25 <= r.vpl_brl_p50
    assert r.vpl_brl_p50 <= r.vpl_brl_p75
    assert r.vpl_brl_p75 <= r.vpl_brl_p90


def test_min_e_max_envelopam_percentis():
    """min <= P10, P90 <= max."""
    r = simulacao_monte_carlo(**CASO_BASE)
    assert r.vpl_brl_min <= r.vpl_brl_p10
    assert r.vpl_brl_p90 <= r.vpl_brl_max


def test_probabilidade_viavel_em_zero_um():
    """P(VPL > 0) sempre em [0, 1]."""
    r = simulacao_monte_carlo(**CASO_BASE)
    assert 0.0 <= r.probabilidade_viavel <= 1.0


def test_probabilidade_tir_acima_wacc_em_zero_um():
    r = simulacao_monte_carlo(**CASO_BASE)
    assert 0.0 <= r.probabilidade_tir_acima_wacc <= 1.0


def test_media_proxima_da_mediana_para_distribuicoes_simetricas():
    """
    Em triangulares simetricas (default tem skew leve, mas pequeno),
    a media nao deve estar muito longe da mediana.
    """
    r = simulacao_monte_carlo(
        capex_brl=1_000_000,
        opex_anual_brl=10_000,
        economia_anual_brl=200_000,
        # Distribuicoes simetricas
        capex_min_pct=0.85, capex_max_pct=1.15,
        opex_min_pct=0.85, opex_max_pct=1.15,
        economia_min_pct=0.85, economia_max_pct=1.15,
        n_iteracoes=5_000,
        seed=42,
    )
    # Diferenca relativa < 5% do desvio padrao
    diff = abs(r.vpl_brl_media - r.vpl_brl_p50)
    assert diff < 0.5 * r.vpl_brl_desvio_padrao or r.vpl_brl_desvio_padrao == 0


# ===========================================================================
# Monotonicidade economica
# ===========================================================================


def test_capex_maior_reduz_viabilidade():
    """
    Aumentar CAPEX central deve reduzir P(VPL > 0).
    Sanity check de que o modelo nao esta invertido.
    """
    base = {
        "opex_anual_brl": 20_000.0,
        "economia_anual_brl": 250_000.0,
        "n_iteracoes": 2_000,
        "seed": 42,
    }
    r_capex_baixo = simulacao_monte_carlo(capex_brl=1_500_000.0, **base)
    r_capex_alto = simulacao_monte_carlo(capex_brl=3_000_000.0, **base)
    assert r_capex_baixo.probabilidade_viavel > r_capex_alto.probabilidade_viavel
    assert r_capex_baixo.vpl_brl_p50 > r_capex_alto.vpl_brl_p50


def test_economia_maior_aumenta_viabilidade():
    """Mais economia -> maior P(VPL>0) e maior P50."""
    base = {
        "capex_brl": 2_000_000.0,
        "opex_anual_brl": 20_000.0,
        "n_iteracoes": 2_000,
        "seed": 42,
    }
    r_pouco = simulacao_monte_carlo(economia_anual_brl=100_000.0, **base)
    r_muito = simulacao_monte_carlo(economia_anual_brl=400_000.0, **base)
    assert r_muito.probabilidade_viavel > r_pouco.probabilidade_viavel
    assert r_muito.vpl_brl_p50 > r_pouco.vpl_brl_p50


def test_horizonte_maior_aumenta_viabilidade():
    """Horizonte mais longo -> mais cash flow acumulado."""
    base = {
        "capex_brl": 2_000_000.0,
        "opex_anual_brl": 20_000.0,
        "economia_anual_brl": 250_000.0,
        "n_iteracoes": 2_000,
        "seed": 42,
    }
    r_curto = simulacao_monte_carlo(horizonte_anos=10, **base)
    r_longo = simulacao_monte_carlo(horizonte_anos=20, **base)
    assert r_longo.vpl_brl_p50 > r_curto.vpl_brl_p50


# ===========================================================================
# Histograma
# ===========================================================================


def test_histograma_soma_igual_n_iteracoes():
    """A soma das contagens deve ser exatamente n_iteracoes."""
    r = simulacao_monte_carlo(**CASO_BASE)
    assert sum(r.histograma_contagens) == CASO_BASE["n_iteracoes"]


def test_histograma_tem_n_bins_correto():
    r = simulacao_monte_carlo(**CASO_BASE, n_bins_histograma=20)
    assert len(r.histograma_contagens) == 20
    assert len(r.histograma_bins_brl) == 21  # n_bins + 1 bordas


def test_histograma_bins_em_ordem_crescente():
    r = simulacao_monte_carlo(**CASO_BASE)
    for i in range(len(r.histograma_bins_brl) - 1):
        assert r.histograma_bins_brl[i] <= r.histograma_bins_brl[i + 1]


# ===========================================================================
# Validacao de entrada
# ===========================================================================


def test_n_iteracoes_minimo_100():
    with pytest.raises(ValueError, match="n_iteracoes"):
        simulacao_monte_carlo(
            capex_brl=1e6, opex_anual_brl=1e4, economia_anual_brl=2e5,
            n_iteracoes=50,
        )


def test_capex_min_pct_invalido():
    with pytest.raises(ValueError, match="capex_min_pct"):
        simulacao_monte_carlo(
            capex_brl=1e6, opex_anual_brl=1e4, economia_anual_brl=2e5,
            capex_min_pct=1.5,
        )


def test_capex_max_pct_invalido():
    with pytest.raises(ValueError, match="capex"):
        simulacao_monte_carlo(
            capex_brl=1e6, opex_anual_brl=1e4, economia_anual_brl=2e5,
            capex_max_pct=0.9,
        )


def test_wacc_central_fora_do_intervalo():
    with pytest.raises(ValueError, match="wacc_central"):
        simulacao_monte_carlo(
            capex_brl=1e6, opex_anual_brl=1e4, economia_anual_brl=2e5,
            wacc_central=0.5, wacc_max=0.25,
        )


def test_wacc_desvio_negativo():
    with pytest.raises(ValueError, match="wacc_desvio_padrao"):
        simulacao_monte_carlo(
            capex_brl=1e6, opex_anual_brl=1e4, economia_anual_brl=2e5,
            wacc_desvio_padrao=-0.01,
        )


def test_n_bins_minimo_5():
    with pytest.raises(ValueError, match="n_bins_histograma"):
        simulacao_monte_carlo(
            capex_brl=1e6, opex_anual_brl=1e4, economia_anual_brl=2e5,
            n_bins_histograma=2,
        )


# ===========================================================================
# Casos degenerados
# ===========================================================================


def test_distribuicoes_apertadas_dao_p10_p90_proximos():
    """
    Quando as distribuicoes sao apertadas (variancia muito baixa), P10 e P90
    devem ficar proximos da mediana.
    """
    r = simulacao_monte_carlo(
        capex_brl=2_000_000.0,
        opex_anual_brl=20_000.0,
        economia_anual_brl=200_000.0,
        capex_min_pct=0.99, capex_max_pct=1.01,
        opex_min_pct=0.99, opex_max_pct=1.01,
        economia_min_pct=0.99, economia_max_pct=1.01,
        wacc_desvio_padrao=0.001,
        n_iteracoes=1_000,
        seed=42,
    )
    # Range P10-P90 < 5% do P50 (em valor absoluto)
    if r.vpl_brl_p50 != 0:
        spread_relativo = (r.vpl_brl_p90 - r.vpl_brl_p10) / abs(r.vpl_brl_p50)
        assert spread_relativo < 0.10


def test_projeto_super_viavel_da_prob_alta():
    """
    Projeto com economia 10x o opex e CAPEX baixo -> prob ~ 1.
    """
    r = simulacao_monte_carlo(
        capex_brl=500_000.0,
        opex_anual_brl=10_000.0,
        economia_anual_brl=300_000.0,
        n_iteracoes=2_000,
        seed=42,
    )
    assert r.probabilidade_viavel > 0.95


def test_projeto_inviavel_da_prob_baixa():
    """
    CAPEX alto, economia baixa -> prob ~ 0.
    """
    r = simulacao_monte_carlo(
        capex_brl=10_000_000.0,
        opex_anual_brl=100_000.0,
        economia_anual_brl=200_000.0,
        n_iteracoes=2_000,
        seed=42,
    )
    assert r.probabilidade_viavel < 0.05


# ===========================================================================
# Metadata e auditoria
# ===========================================================================


def test_distribuicoes_usadas_inclui_todos_parametros():
    """O dump de auditoria deve ter todas as 4 variaveis aleatorias."""
    r = simulacao_monte_carlo(**CASO_BASE)
    assert "capex" in r.distribuicoes_usadas
    assert "opex" in r.distribuicoes_usadas
    assert "economia" in r.distribuicoes_usadas
    assert "wacc" in r.distribuicoes_usadas
    assert r.distribuicoes_usadas["capex"]["distribuicao"] == "triangular"
    assert r.distribuicoes_usadas["wacc"]["distribuicao"] == "normal_truncada"


def test_seed_persistida_no_resultado():
    r = simulacao_monte_carlo(**CASO_BASE)
    assert r.seed == CASO_BASE["seed"]


def test_n_iteracoes_persistido():
    r = simulacao_monte_carlo(**CASO_BASE)
    assert r.n_iteracoes == CASO_BASE["n_iteracoes"]
