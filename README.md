# BESS Sizing Copilot

Sistema multi-agente para dimensionamento de Sistemas de Armazenamento de Energia (BESS) no mercado brasileiro.

## Status

Sprint 1.1 — Núcleo de cálculo determinístico (peak shaving).

## Estrutura

```
Projeto HDT/
├── bess-core/                    # Núcleo de cálculo (Python puro, sem LLM)
│   ├── bess_core/
│   │   ├── dimensionamento.py    # Sizing de banco
│   │   ├── despacho.py           # Simulação 8760h (Sprint 1.2)
│   │   ├── financeiro.py         # Payback, TIR, VPL, LCOS (Sprint 1.3)
│   │   └── degradacao.py         # SoH ao longo da vida útil (Sprint 1.4)
│   ├── tests/
│   ├── pyproject.toml
│   ├── pytest.ini
│   └── requirements.txt
└── docs/
    └── MEMORIAL_DIMENSIONAMENTO.md
```

## Como rodar os testes

```bash
cd bess-core
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pytest -v
```

## Roadmap

| Sprint | Entregavel |
|--------|------------|
| 1 | Núcleo de cálculo determinístico (Python + pytest) |
| 2 | Single agent end-to-end com Claude Agent SDK |
| 3 | Frontend Next.js + Supabase |
| 4 | Multi-agente (Discovery + Engenharia + Proposta) |

## Princípios

- **Cálculo antes de LLM.** Toda lógica crítica é determinística e auditável.
- **TCC-grade.** Type hints, docstrings com fórmulas, testes validados manualmente.
- **Conformidade BR.** REN 1.000/2021, Lei 14.300/2022, NBR 5410, NBR 16690.
