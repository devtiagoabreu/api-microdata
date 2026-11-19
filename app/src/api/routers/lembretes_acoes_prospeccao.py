"""Lembretes de email para ações de prospecção agendadas (CRM dgbcomex).

Executa no banco Neon (schema public, tabela crm_acoes_prospeccao) e envia email
via SMTP configurado no .env (GMAIL_USER / GMAIL_APP_PASSWORD).

Endpoints protegidos por CRON_SECRET (reusa JWT_SECRET).
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import text

from src.config import get_settings
from src.db import neon

router = APIRouter(tags=["lembretes-acoes-prospeccao"])

settings = get_settings()

CRON_SECRET = settings.jwt_secret

TIPO_DIA_ANTERIOR = "dia-anterior"
TIPO_DIA_ACAO = "dia-da-acao"
ALIASES_TIPO = {"dia-da-visita": TIPO_DIA_ACAO}


def _autorizado(authorization: str | None) -> None:
    if not authorization or authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=401, detail="nao autorizado")


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        return str(valor)
    limpo = valor.strip()
    return limpo or None


def _url_acao(acao_id: Any) -> str:
    base = os.getenv("APP_URL") or (
        settings.cors_origins[0].rstrip("/") if settings.cors_origins else ""
    )
    return f"{base}/comercial/crm/acoes-prospeccao/{acao_id}"


def _montar_html(tipo: str, acao: dict[str, Any], usuario: dict[str, Any]) -> str:
    data_acao = _texto(acao.get("data_acao")) or ""
    try:
        data_fmt = datetime.fromisoformat(data_acao).strftime("%d/%m/%Y")
    except Exception:
        data_fmt = data_acao
    hora = _texto(acao.get("hora")) or ""
    cliente = (
        acao.get("cliente_nome")
        or acao.get("empresa_nome")
        or acao.get("nome_avulso")
        or "—"
    )
    endereco = ", ".join(
        filter(
            None,
            [
                _texto(acao.get("endereco")),
                _texto(acao.get("numero")),
                _texto(acao.get("bairro")),
                _texto(acao.get("cidade")),
                _texto(acao.get("uf")),
            ],
        )
    ) or "—"
    url_acao = _url_acao(acao.get("id"))

    dia_anterior = tipo == TIPO_DIA_ANTERIOR
    trecho_tempo = "amanhã" if dia_anterior else "hoje"

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8fafc;">
      <div style="background-color: #ffffff; border-radius: 8px; padding: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
        <h2 style="color: #1e293b; margin-top: 0; font-size: 20px;">
          Lembrete de Ação de Prospecção - {trecho_tempo.capitalize()}
        </h2>
        <p style="color: #475569; font-size: 14px; line-height: 1.6;">
          Olá, <strong>{_texto(usuario.get("name")) or "usuário"}</strong>.
          Você tem uma ação de prospecção agendada para {trecho_tempo}.
        </p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; color: #334155;">
          <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 8px 0; font-weight: 600; color: #64748b; width: 35%;">Data</td>
            <td style="padding: 8px 0;">{data_fmt}</td>
          </tr>
          {f'<tr style="border-bottom: 1px solid #e2e8f0;"><td style="padding: 8px 0; font-weight: 600; color: #64748b;">Horário</td><td style="padding: 8px 0;">{hora}</td></tr>' if hora else ""}
          <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 8px 0; font-weight: 600; color: #64748b;">Tipo</td>
            <td style="padding: 8px 0;">{_texto(acao.get("tipo")) or ""}</td>
          </tr>
          <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 8px 0; font-weight: 600; color: #64748b;">Status</td>
            <td style="padding: 8px 0;">{_texto(acao.get("status")) or ""}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #64748b;">Cliente / Pessoa</td>
            <td style="padding: 8px 0;">{cliente}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; font-weight: 600; color: #64748b;">Endereço</td>
            <td style="padding: 8px 0;">{endereco}</td>
          </tr>
        </table>
        <p style="margin: 24px 0 12px;">
          <a href="{url_acao}" style="background-color: #7c3aed; color: #ffffff; padding: 10px 18px; border-radius: 6px; text-decoration: none; font-size: 14px;">
            Ver ação de prospecção
          </a>
        </p>
        <p style="color: #64748b; font-size: 13px;">
          Este é um lembrete automático do sistema PDM Têxtil. Boa prospecção!
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
        print(f"[LEMBRETE-ACAO-PROSPECCAO] Erro ao enviar para {destinatario}: {exc}")
        return False


def _coluna_lembrete(tipo: str) -> str:
    return (
        "lembrete_dia_anterior_enviado"
        if tipo == TIPO_DIA_ANTERIOR
        else "lembrete_dia_acao_enviado"
    )


def _buscar_acoes_para_data(
    con, data_alvo: str, coluna: str
) -> list[dict[str, Any]]:
    """Busca ações agendadas para uma data no Neon que ainda nao receberam lembrete."""
    sql = f"""
    select a.id, a.data_acao, a.hora, a.tipo, a.status, a.endereco, a.numero,
           a.complemento, a.bairro, a.cidade, a.uf, a.cliente_id, a.empresa_id,
           a.nome_avulso, a.criado_por,
           u.email as usuario_email, u.name as usuario_nome,
           c.nome as cliente_nome, p.razao_social as empresa_nome
    from public.crm_acoes_prospeccao a
    left join public.usuarios u on u.id = a.criado_por
    left join public.clientes c on c.id = a.cliente_id
    left join public.crm_pessoas p on p.id = a.empresa_id
    where a.data_acao = :data_alvo
      and a.status = 'AGENDADA'
      and (a.{coluna} is null or a.{coluna} = false)
    order by a.id
    """
    rows = con.execute(text(sql), {"data_alvo": data_alvo}).mappings().all()
    return [dict(r) for r in rows]


def _marcar_enviado(con, acao_id: int, coluna: str) -> None:
    con.execute(
        text(f"update public.crm_acoes_prospeccao set {coluna} = true where id = :id"),
        {"id": acao_id},
    )


def processar_lembretes(tipo: str) -> dict[str, int]:
    """tipo: 'dia-anterior' (ações para amanhã) ou 'dia-da-acao' (ações para hoje)."""
    tipo = ALIASES_TIPO.get(tipo, tipo)
    hoje = date.today().isoformat()
    if tipo == TIPO_DIA_ANTERIOR:
        data_alvo = (date.today() + timedelta(days=1)).isoformat()
    else:
        data_alvo = hoje

    coluna = _coluna_lembrete(tipo)

    with neon.engine().connect() as conn:
        acoes = _buscar_acoes_para_data(conn, data_alvo, coluna)

    enviados = 0
    erros = 0

    for acao in acoes:
        email = acao.get("usuario_email")
        nome = acao.get("usuario_nome") or "usuário"
        if not email:
            erros += 1
            continue

        data_fmt = (
            datetime.fromisoformat(str(acao.get("data_acao"))).strftime("%d/%m/%Y")
            if acao.get("data_acao")
            else ""
        )
        assunto = (
            f"Lembrete: ação de prospecção agendada para amanhã ({data_fmt})"
            if tipo == TIPO_DIA_ANTERIOR
            else f"Lembrete: ação de prospecção hoje ({data_fmt})"
        )
        html = _montar_html(tipo, acao, {"name": nome, "email": email})

        if _enviar_email(email, assunto, html):
            enviados += 1
        else:
            erros += 1

        with neon.engine().connect() as conn:
            _marcar_enviado(conn, acao["id"], coluna)
            conn.commit()

    return {"tipo": tipo, "total": len(acoes), "enviados": enviados, "erros": erros}


@router.post("/lembretes-acoes-prospeccao/dia-anterior")
def lembrete_dia_anterior(authorization: str | None = Header(default=None)) -> dict:
    """Envia lembrete para ações agendadas para amanhã (rodar às 13:55 Brasília)."""
    _autorizado(authorization)
    return processar_lembretes(TIPO_DIA_ANTERIOR)


@router.post("/lembretes-acoes-prospeccao/dia-da-acao")
def lembrete_dia_da_acao(authorization: str | None = Header(default=None)) -> dict:
    """Envia lembrete para ações agendadas para hoje (rodar às 7:30 Brasília)."""
    _autorizado(authorization)
    return processar_lembretes(TIPO_DIA_ACAO)
