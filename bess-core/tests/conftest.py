"""
Configuração compartilhada de testes.

Garante que ``bess_core`` seja importável quando ``pytest`` é executado a
partir de ``bess-core/`` (sem precisar de ``pip install -e .``).
"""

import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))
