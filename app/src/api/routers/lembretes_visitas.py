"""Lembretes de email para visitas agendadas (CRM dgbcomex).

Executa no banco Neon (schema public, tabela crm_visitas) e envia email
via SMTP configurado no .env (GMAIL_USER / GMAIL_APP_PASSWORD).

Endpoints protegidos por CRON_SECRET.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import text

from src.config import get_settings
from src.db import neon

router = APIRouter(tags=["lembretes-visitas"])

settings = get_settings()

CRON_SECRET = settings.jwt_secret  # reusa o mesmo segredo já configurado


def _autorizado(authorization: str | None) -> None:
    if not authorization or authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=401, detail="nao autorizado")


def _data_iso(d: date | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()
    return str(d)[:10]


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        return str(valor)
    limpo = valor.strip()
    return limpo or None


def _montar_html(tipo: str, visita: dict[str, Any], usuario: dict[str, Any]) -> str:
    data_visita = _texto(visita.get("data_visita")) or ""
    try:
        data_fmt = datetime.fromisoformat(data_visita).strftime("%d/%m/%Y")
    except Exception:
        data_fmt = data_visita
    hora = _texto(visita.get("hora")) or ""
    cliente = (
        visita.get("cliente_nome")
        or visita.get("empresa_nome")
        or visita.get("nome_avulso")
        or "—"
    )
    endereco = ", ".join(
        filter(
            None,
            [
                _texto(visita.get("endereco")),
                _texto(visita.get("numero")),
                _texto(visita.get("bairro")),
                _texto(visita.get("cidade")),
                _texto(visita.get("uf")),
            ],
        )
    ) or "—"

    dia_anterior = tipo == "dia-anterior"
    trecho_tempo = "amanha" if dia_anterior else "hoje"
    trecho_assunto = "amanha" if dia_anterior else "hoje"

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8fafc;">
      <div style="background-color: #ffffff; border-radius: 8px; padding: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <h2 style="color: #1e293b; margin-top: 0; font-size: 20px;">
          Lembrete de Visita - {trecho_tempo.capitalize()}
        </h2>
        <p style="color: #475569; font-size: 14px; line-height: 1.6;">
          Olá, <strong>{_texto(usuario.get("name")) or "usuario"}</strong>.
          Voce tem uma visita agendada para {trecho_tempo}.
        </p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; color: #334155;">
          <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 8px 0; font-weight: 600; color: #64748b; width: 35%;">Data</td>
            <td style="padding: 8px 0;">{data_fmt}</td>
          </tr>
          {f'<tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px 0; font-weight: 600; color: #64748b;">Horario</td><td style="padding: 8px 0;">{hora}</td></tr>' if hora else ""}
          <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 8px 0; font-weight: 600; color: #64748b;">Tipo</td>
            <td style="padding: 8px 0;">{_texto(visita.get("tipo")) or ""}</td>
          </tr>
          <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 8px 0; font-weight: 600; color: #64748b;">Status</td>
            <td style="padding: 8px 0;">{_texto(visita.get("status")) or ""}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #64748b;">Cliente / Pessoa</td>
            <td style="padding: 8px 0;">{cliente}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #64748b;">Endereco</td>
            <td style="padding: 8px 0;">{endereco}</td>
          </tr>
        </table>
        <p style="color: #64748b; font-size: 13px;">
          Este e um lembrete automatico do sistema PDM Têxtil. Boa visita!
        </p>
      </div>
    </div>
    """


def _enviar_email(destinatario: str, assunto: str, html: str) -> bool:
    try:
        msg = EmailMessage()
        msg["From"] = f"PDM Têxtil <{settings.gmail_user}>"
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.set_content(html, subtype="html")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(settings.gmail_user, settings.gmail_app_password)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[LEMBRETE-VISITA] Erro ao enviar para {destinatario}: {exc}")
        return False


def _buscar_visitas_para_data(con, data_alvo: str) -> list[dict[str, Any]]:
    """Busca visitas agendadas para uma data no Neon que ainda nao receberam lembrete."""
    coluna = (
        "lembrete_dia_anterior_enviado"
        if data_alvo == "dia-anterior"
        else "lembrete_dia_visita_enviado"
    )
    # data_alvo aqui eh a data da visita (YYYY-MM-DD), nao o tipo
    sql = f"""
    select v.id, v.data_visita, v.hora, v.tipo, v.status, v.endereco, v.numero,
           v.complemento, v.bairro, v.cidade, v.uf, v.cliente_id, v.empresa_id,
           v.nome_avulso, v.criado_por,
           u.email as usuario_email, u.name as usuario_nome,
           c.nome as cliente_nome, p.razao_social as empresa_nome
    from public.crm_visitas v
    left join public.usuarios u on u.id = v.criado_por
    left join public.clientes c on c.id = v.cliente_id
    left join public.crm_pessoas p on p.id = v.empresa_id
    where v.data_visita = :data_alvo
      and v.status = 'AGENDADA'
      and (v.{coluna} is null or v.{coluna} = false)
    order by v.id
    """
    rows = con.execute(text(sql), {"data_alvo": data_alvo}).mappings().all()
    return [dict(r) for r in rows]


def _marcar_enviado(con, visita_id: int, coluna: str) -> None:
    con.execute(
        text(f"update public.crm_visitas set {coluna} = true where id = :id"),
        {"id": visita_id},
    )


def processar_lembretes(tipo: str) -> dict[str, int]:
    """tipo: 'dia-anterior' (visitas para amanha) ou 'dia-da-visita' (visitas para hoje)."""
    hoje = date.today().isoformat()
    if tipo == "dia-anterior":
        data_alvo = (date.today() + timedelta(days=1)).isoformat()
    else:
        data_alvo = hoje

    coluna = (
        "lembrete_dia_anterior_enviado"
        if tipo == "dia-anterior"
        else "lembrete_dia_visita_enviado"
    )

    with neon.engine().connect() as conn:
        visitas = _buscar_visitas_para_data(conn, data_alvo)

    enviados = 0
    erros = 0

    for visita in visitas:
        email = visita.get("usuario_email")
        nome = visita.get("usuario_nome") or "usuario"
        if not email:
            erros += 1
            continue

        data_fmt = (
            datetime.fromisoformat(str(visita.get("data_visita"))).strftime("%d/%m/%Y")
            if visita.get("data_visita")
            else ""
        )
        assunto = (
            f"Lembrete: visita agendada para amanha ({data_fmt})"
            if tipo == "dia-anterior"
            else f"Lembrete: visita hoje ({data_fmt})"
        )
        html = _montar_html(tipo, visita, {"name": nome, "email": email})

        if _enviar_email(email, assunto, html):
            enviados += 1
        else:
            erros += 1

        with neon.engine().connect() as conn:
            _marcar_enviado(conn, visita["id"], coluna)
            conn.commit()

    return {"tipo": tipo, "total": len(visitas), "enviados": enviados, "erros": erros}


@router.post("/lembretes-visitas/dia-anterior")
def lembrete_dia_anterior(authorization: str | None = Header(default=None)) -> dict:
    """Envia lembrete para visitas agendadas para amanha (rodar as 13:55 Brasilia)."""
    _autorizado(authorization)
    return processar_lembretes("dia-anterior")


@router.post("/lembretes-visitas/dia-da-visita")
def lembrete_dia_da_visita(authorization: str | None = Header(default=None)) -> dict:
    """Envia lembrete para visitas agendadas para hoje (rodar as 7:30 Brasilia)."""
    _autorizado(authorization)
    return processar_lembretes("dia-da-visita")
