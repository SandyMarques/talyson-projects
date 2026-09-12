"""Configuração global dos testes.

Força UTF-8 na leitura dos módulos de teste. Sem isso, o Python no Windows lê os arquivos com
o encoding do sistema (cp1252) e as asserções que comparam mensagens acentuadas em português
falham por corrupção de byte, não por defeito de comportamento.

Também fixa `PYTHONHASHSEED` por consistência de ordenação em estruturas derivadas de hash.
"""

import os
import sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

if hasattr(sys, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):  # pragma: no cover - ambiente exótico
        pass
