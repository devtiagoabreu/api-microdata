"""Script de cron para lembretes de ações de prospecção (Agendador de Tarefas do Windows).

Uso:
    python scripts/enviar_lembretes_acoes_prospeccao.py dia-anterior  # rodar às 13:55 Brasília
    python scripts/enviar_lembretes_acoes_prospeccao.py dia-da-acao   # rodar às  7:30 Brasília
    python scripts/enviar_lembretes_acoes_prospeccao.py dia-da-visita # alias de dia-da-acao

Lê o banco Neon (crm_acoes_prospeccao) e envia email via SMTP (.env GMAIL_*).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from src.api.routers.lembretes_acoes_prospeccao import processar_lembretes

TIPOS = ("dia-anterior", "dia-da-acao", "dia-da-visita")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in TIPOS:
        print(
            "Uso: python scripts/enviar_lembretes_acoes_prospeccao.py "
            "<dia-anterior|dia-da-acao|dia-da-visita>"
        )
        sys.exit(2)

    tipo = sys.argv[1]
    resultado = processar_lembretes(tipo)
    print(resultado)


if __name__ == "__main__":
    main()
