"""bess-core: nucleo de calculo deterministico do BESS Sizing Copilot."""

from bess_core.degradacao import (
    ResultadoDegradacao,
    calcular_soh_anual,
)
from bess_core.despacho import (
    ResultadoDespacho,
    simular_despacho_horario,
)
from bess_core.dimensionamento import (
    DimensionamentoArbitragem,
    DimensionamentoBackup,
    DimensionamentoBESS,
    dimensionar_arbitragem,
    dimensionar_backup,
    dimensionar_peak_shaving,
)
from bess_core.financeiro import (
    AnaliseFinanceira,
    SensibilidadeItem,
    analisar_financeiro,
)

__version__ = "1.0.0"

__all__ = [
    # Sprint 1.1
    "DimensionamentoBESS",
    "DimensionamentoArbitragem",
    "DimensionamentoBackup",
    "dimensionar_peak_shaving",
    "dimensionar_arbitragem",
    "dimensionar_backup",
    # Sprint 1.2
    "ResultadoDespacho",
    "simular_despacho_horario",
    # Sprint 1.3
    "AnaliseFinanceira",
    "SensibilidadeItem",
    "analisar_financeiro",
    # Sprint 1.4
    "ResultadoDegradacao",
    "calcular_soh_anual",
]
