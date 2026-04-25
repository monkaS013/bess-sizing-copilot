# bess-core

Núcleo de cálculo determinístico do BESS Sizing Copilot.

Sem LLM, sem rede, sem persistência — apenas matemática auditável e replicável. É a base sobre a qual os agentes Claude operam via tool-use.

## Módulos

| Módulo | Responsabilidade | Status |
|--------|------------------|--------|
| `dimensionamento` | Sizing do banco (kWh úteis, kWh nominais, kW, C-rate) | Sprint 1.1 ✓ |
| `despacho` | Simulação horária 8760h (peak shaving, arbitragem, autoconsumo) | Sprint 1.2 |
| `financeiro` | Payback, TIR, VPL, LCOS, Monte Carlo | Sprint 1.3 |
| `degradacao` | Evolução de SoH (cíclica + calendárica) | Sprint 1.4 |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
pytest -v
```

## Decisões de design

1. **Python puro nos cálculos críticos.** Numpy/pandas só onde performance importa (despacho 8760h).
2. **Dataclasses imutáveis para resultados.** Evita mutação acidental e facilita logging.
3. **Premissas explícitas.** Toda função retorna o dicionário de premissas usado, para auditoria.
4. **Tolerância 2% nos testes.** Compatível com incerteza de fichas técnicas de fabricantes.
