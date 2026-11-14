"""Script de cron para lembretes de visitas (chamado pelo Agendador de Tarefas do Windows).

Uso:
    python scripts/enviar_lembretes_visitas.py dia-anterior   # rodar as 13:55 Brasilia
    python scripts/enviar_lembretes_visitas.py dia-da-visita  # rodar as  7:30 Brasilia

Lê o banco Neon (crm_visitas) e envia email via SMTP (.env GMAIL_*).
"""

from __future__ import annotations

import sys

from src.api.routers.lembretes_visitas import processar_lembretes


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("dia-anterior", "dia-da-visita"):
        print("Uso: python scripts/enviar_lembretes_visitas.py <dia-anterior|dia-da-visita>")
        sys.exit(2)

    tipo = sys.argv[1]
    resultado = processar_lembretes(tipo)
    print(resultado)


if __name__ == "__main__":
    main()
