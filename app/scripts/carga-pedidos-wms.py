"""Carga de pedidos liberados do ERP para o banco local do WMS (dgbcomex_warehouse).

Espelha raw.car_pedido e raw.car_itens_pedido do ERP (SQL Server) para o banco
local, idempotentemente (UPSERT por empresa+pedido e empresa+pedido+item).

Uso:
    $env:PYTHONPATH='M:\dev\api-microdata\app'
    .venv\Scripts\python.exe scripts\carga-pedidos-wms.py [--limite-dias=30] [--apenas-novos]
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from typing import Any

import pyodbc
from sqlalchemy import text

from src.db.warehouse import engine

# --- Credenciais do ERP (mesmas do .env da api-microdata) ---
ERP_SERVER = "10.156.0.124"
ERP_DATABASE = "DBMicrodata_DGB"
ERP_USERNAME = "sadgb"
ERP_PASSWORD = "P@##saDGB#2025"

ERP_CONN_STR = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={ERP_SERVER};"
    f"DATABASE={ERP_DATABASE};"
    f"UID={ERP_USERNAME};"
    f"PWD={ERP_PASSWORD};"
    "TrustServerCertificate=yes;"
    "Timeout=60;"
)

# Colunas do banco local (snake_case) -> coluna do ERP (PascalCase)
MAP_PEDIDO: dict[str, str | None] = {
    "empresa": "Empresa",
    "pedido": "Pedido",
    "cliente": "Cliente",
    "data_pedido": "Data_Pedido",
    "cond_pagto": "Cond_Pagto",
    "data_entrega": "Data_Entrega",
    "cod_transp": "Cod_Transp",
    "des_transp": "Des_Transp",
    "cod_redesp": "Cod_Redesp",
    "des_redesp": "Des_Redesp",
    "end1_redesp": "End1_Redesp",
    "end2_redesp": "End2_Redesp",
    "porc_desc": "Porc_Desc",
    "porc_acresc": "Porc_Acresc",
    "seu_pedido": "Seu_Pedido",
    "contato": "Contato",
    "classificacao": "Classificacao",
    "status": "Status",
    "banco_1": "Banco_1",
    "agencia_1": "Agencia_1",
    "dig_age_1": "DigAge_1",
    "conta_1": "Conta_1",
    "dig_con_1": "DigCon_1",
    "operacao_1": "Operacao_1",
    "banco_2": "Banco_2",
    "agencia_2": "Agencia_2",
    "dig_age_2": "DigAge_2",
    "conta_2": "Conta_2",
    "dig_con_2": "DigCon_2",
    "operacao_2": "Operacao_2",
    "cobranca_1": "Cobranca_1",
    "cobranca_2": "Cobranca_2",
    "cheque_1": "Cheque_1",
    "cheque_2": "Cheque_2",
    "pagto_1": "Pagto_1",
    "pagto_2": "Pagto_2",
    "ver_obs_1": "VerObs_1",
    "ver_obs_2": "VerObs_2",
    "frete_conta": "Frete_Conta",
    "tipo_pedido": "Tipo_Pedido",
    "cond_pagto_extenso": "Cond_Pagto_Extenso",
    "via": "Via",
    "s_pro": "SPro",
    "s_sit": "SSit",
    "s_cor": "SCor",
    "s_des": "SDes",
    "s_cat": "SCat",
    "end1_cobranca": "End1_Cobranca",
    "end2_cobranca": "End2_Cobranca",
    "end1_entrega": "End1_Entrega",
    "end2_entrega": "End2_Entrega",
    "redespacho_conta": "Redespacho_Conta",
    "usuario": "Usuario",
    "vr_frete": "Vr_Frete",
    "usuario_alt": "Usuario_Alt",
    "remessa": "Remessa",
    "datas_entrega": "Datas_Entrega",
    "pecas": "Pecas",
    "datas_entrega2": "Datas_Entrega2",
    "porcentagem_comissao": "Porcentagem_Comissao",
    "usa_enfestado_rolo": "Usa_Enfestado_Rolo",
    "local_entrega": "Local_Entrega",
    "status_email": "Status_Email",
    "politica": "Politica",
    "s_larg": "SLarg",
    "tabela_tinturaria": "Tabela_Tinturaria",
    "prazo_medio": "Prazo_Medio",
    "pedido_urgente": "Pedido_Urgente",
    "aceita_pedido_parcial": "Aceita_Pedido_Parcial",
    "bloqueado": "Bloqueado",
    "cliente_triangulo": "Cliente_Triangulo",
    "tipo_comercializacao": "Tipo_Comercializacao",
    "s_variante": "SVariante",
    "motivo_reprova": "MotivoReprova",
    "status_ped": "Status_Ped",
    "entregas_futuras": "Entregas_Futuras",
    "modalidade_ent_princ": "Modalidade_Ent_Princ",
    "modalidade_ent_detal": "Modalidade_Ent_Detal",
    "pedido_representante": "Pedido_Representante",
    "cod_tabela_preco_def_usuario": "cod_tabela_preco_def_usuario",
    "dt_ultima_aprov_comerc": "dt_ultima_aprov_comerc",
    "tipo_pedido_comercial": "Tipo_Pedido_Comercial",
    "validado_gestor": "validado_gestor",
    "data_hora_alteracao": "DataHora_Alteracao",
    "descricao_reprova": "DescricaoReprova",
    "cliente_entrega": "ClienteEntrega",
    "perc_rentabilidade_geral": "PercRentabilidadeGeral",
    "linha_produto": "LinhaProduto",
    "pedido_ecommerce": "Pedido_Ecommerce",
    "alerta_cd": "alerta_cd",
    "tp_orig_ped_cd": "tp_orig_ped_cd",
    "motivo_alt_cd": "motivo_alt_cd",
    "cond_cd": "cond_cd",
    "usu_cd": "usu_cd",
    "ped_orig_nu": "ped_orig_nu",
    "email_enviado": "email_enviado",
    "marcacao_cd": "marcacao_cd",
    "pedido_id": "pedido_id",
    "regra_negocio": "regra_negocio",
}

MAP_ITEM: dict[str, str | None] = {
    "empresa": "Empresa",
    "pedido": "Pedido",
    "item": "Item",
    "produto": "Produto",
    "situacao": "Situacao",
    "cor": "Cor",
    "desenho": "Desenho",
    "categoria": "Categoria",
    "qtde": "Qtde",
    "vr_unitario": "Vr_Unitario",
    "vr_unitario2": "Vr_Unitario2",
    "vr_total": "Vr_Total",
    "classificacao": "Classificacao",
    "data_entrega": "Data_Entrega",
    "observacao": "Observacao",
    "qtde_romaneio": "Qtde_Romaneio",
    "qtde_acerto": "Qtde_Acerto",
    "largura": "Largura",
    "comissao": "Comissao",
    "data_acerto": "Data_Acerto",
    "usuario_acerto": "Usuario_Acerto",
    "comissao_s": "ComissaoS",
    "tipo": "Tipo",
    "usuario": "Usuario",
    "produto_cliente": "Produto_Cliente",
    "unid": "Unid",
    "unid_fat": "Unid_Fat",
    "qtde_fat": "Qtde_Fat",
    "vr_unitario_fat": "Vr_Unitario_Fat",
    "exclusivo": "Exclusivo",
    "distrib_metros_in": "Distrib_MetrosIn",
    "distrib_metros_fn": "Distrib_MetrosFn",
    "variante": "Variante",
    "status_item": "Status_Item",
    "vr_unit_servico": "Vr_Unit_Servico",
    "vr_unit_prod_aplicado": "Vr_Unit_Prod_Aplicado",
    "tipo_fornec": "Tipo_Fornec",
    "fornecedor": "Fornecedor",
    "indice1": "Indice1",
    "indice2": "Indice2",
    "indice3": "Indice3",
    "vr_desconto": "Vr_Desconto",
    "porc_desconto": "Porc_Desconto",
    "obs_web": "Obs_Web",
    "item_ped_compra": "Item_Ped_Compra",
    "dif_perc_tabela_preco": "dif_perc_tabela_preco",
    "aprovado_comercial": "aprovado_comercial",
    "dt_ver_aprov_com": "dt_ver_aprov_com",
    "val_tabela_preco": "val_tabela_preco",
    "val_tabela_preco_total": "val_tabela_preco_total",
    "dif_val_tabela_preco": "dif_val_tabela_preco",
    "perc_comissao": "perc_comissao",
    "val_frete": "val_frete",
    "cod_tab_preco": "cod_tab_preco",
    "tamanho_min_peca": "tamanho_min_peca",
    "comissao_original": "comissao_original",
    "comissaos_original": "comissaos_original",
    "comissao_manual": "comissao_manual",
    "perc_min_aprovacao": "perc_min_aprovacao",
    "dt_entrega": "DtEntrega",
    "liberado": "Liberado",
    "grupo_item": "Grupo_Item",
    "data_previsao_fabril": "Data_Previsao_Fabril",
    "val_tab_desc_comercial": "val_tab_desc_comercial",
    "peso_padrao": "Peso_Padrao",
    "nro_unidades": "Nro_Unidades",
    "perc_rentabilidade": "PercRentabilidade",
    "aprovado_comercial_rentabilidade": "AprovadoComercialRentabilidade",
    "motivo_reprova_rentabilidade": "MotivoReprovaRentabilidade",
    "perc_impostos": "PercImpostos",
    "custo_produto": "CustoProduto",
    "preco_err": "preco_err",
    "desc_porc": "desc_porc",
    "categ_err": "categ_err",
    "prod_tam": "prod_tam",
    "preco_orig": "preco_orig",
    "acres_porc": "acres_porc",
    "prod_bonif_err": "prod_bonif_err",
    "cond_pgto_parc_cd": "cond_pgto_parc_cd",
    "cond_pgto_cd": "cond_pgto_cd",
    "estoque_dt": "estoque_dt",
    "estoque_existe": "estoque_existe",
    "estoque_ped_nu": "estoque_ped_nu",
    "estoque_item_nu": "estoque_item_nu",
}

COLS_PEDIDO = list(MAP_PEDIDO.keys())
COLS_ITEM = list(MAP_ITEM.keys())


def _erp_val(row: dict[str, Any], erp_col: str | None) -> Any:
    """Retorna o valor de uma coluna do ERP a partir de um dict linha."""
    if erp_col is None:
        return None
    return row.get(erp_col)


def conectar_erp() -> pyodbc.Connection:
    return pyodbc.connect(ERP_CONN_STR)


def carregar_pedidos(
    conn_erp: pyodbc.Connection,
    conn_local,
    *,
    limite_dias: int | None = None,
) -> dict[str, int]:
    """Carrega pedidos do ERP para o banco local.

    Regras:
    - Só pedidos com status = '2' (aprovado)
    - Faz UPSERT idempotente (ON CONFLICT) por empresa+pedido e empresa+pedido+item
    """
    estatisticas = {
        "pedidos_lidos": 0,
        "pedidos_inseridos": 0,
        "pedidos_atualizados": 0,
        "itens_inseridos": 0,
        "itens_atualizados": 0,
        "erros": [],
    }

    data_corte = None
    if limite_dias is not None:
        data_corte = (datetime.now() - timedelta(days=limite_dias)).strftime("%Y-%m-%d")

    # 1. Buscar pedidos do ERP
    where_pedido = "p.status = '2'"
    params: list[Any] = []
    if data_corte:
        where_pedido += " and p.data_pedido >= ?"
        params.append(data_corte)

    col_erp_pedido = [MAP_PEDIDO[c] for c in COLS_PEDIDO]
    sql_pedidos = f"""
        select {", ".join(col_erp_pedido)}
        from car_pedido p
        where {where_pedido}
        order by p.data_pedido desc
    """

    cursor = conn_erp.cursor()
    cursor.execute(sql_pedidos, params)
    colunas_erp = [desc[0] for desc in cursor.description]

    pedidos_erp: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        estatisticas["pedidos_lidos"] += 1
        linha = dict(zip(colunas_erp, row))
        d: dict[str, Any] = {}
        for col_local in COLS_PEDIDO:
            d[col_local] = _erp_val(linha, MAP_PEDIDO[col_local])
        pedidos_erp.append(d)

    print(f"  Pedidos lidos do ERP: {estatisticas['pedidos_lidos']}")

    agora = datetime.now()

    # 3. Inserir/atualizar pedidos e itens (UPSERT idempotente)
    with conn_local.begin():
        for p in pedidos_erp:
            cols_sql = ", ".join(COLS_PEDIDO + ["_carga_em"])
            placeholders = ", ".join(f":{c}" for c in COLS_PEDIDO) + ", :_carga_em"
            update_clause = ", ".join(f"{c} = excluded.{c}" for c in COLS_PEDIDO) + ", _carga_em = excluded._carga_em"
            sql = f"""
                insert into raw.car_pedido ({cols_sql})
                values ({placeholders})
                on conflict (empresa, pedido) do update
                set {update_clause}
            """
            params = {c: p[c] for c in COLS_PEDIDO}
            params["_carga_em"] = agora
            resultado = conn_local.execute(text(sql), params)
            if resultado.rowcount == 1:
                estatisticas["pedidos_inseridos"] += 1
            else:
                estatisticas["pedidos_atualizados"] += 1

            # 4. Carregar itens do pedido
            _carregar_itens(
                conn_local, conn_erp, p["empresa"], p["pedido"], estatisticas, agora
            )

    return estatisticas


def _carregar_itens(
    conn_local, conn_erp: pyodbc.Connection, empresa: str, pedido: str,
    estatisticas: dict[str, int], agora: datetime,
) -> None:
    """Carrega os itens de um pedido específico."""
    col_erp_item = [MAP_ITEM[c] for c in COLS_ITEM]
    sql_itens = f"""
        select {", ".join(col_erp_item)}
        from car_itens_pedido
        where empresa = ? and pedido = ?
    """
    cursor = conn_erp.cursor()
    cursor.execute(sql_itens, [empresa, pedido])
    colunas_erp = [desc[0] for desc in cursor.description]

    itens: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        linha = dict(zip(colunas_erp, row))
        d: dict[str, Any] = {}
        for col_local in COLS_ITEM:
            d[col_local] = _erp_val(linha, MAP_ITEM[col_local])
        itens.append(d)

    for it in itens:
        cols_sql = ", ".join(COLS_ITEM + ["_carga_em"])
        placeholders = ", ".join(f":{c}" for c in COLS_ITEM) + ", :_carga_em"
        update_clause = ", ".join(f"{c} = excluded.{c}" for c in COLS_ITEM) + ", _carga_em = excluded._carga_em"
        sql = f"""
            insert into raw.car_itens_pedido ({cols_sql})
            values ({placeholders})
            on conflict (empresa, pedido, item) do update
            set {update_clause}
        """
        params = {c: it[c] for c in COLS_ITEM}
        params["_carga_em"] = agora
        resultado = conn_local.execute(text(sql), params)
        if resultado.rowcount == 1:
            estatisticas["itens_inseridos"] += 1
        else:
            estatisticas["itens_atualizados"] += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga de pedidos WMS do ERP para o banco local")
    parser.add_argument("--limite-dias", type=int, default=None, help="Somente pedidos com data_pedido >= hoje - N dias")
    args = parser.parse_args()

    print("Iniciando carga de pedidos WMS...")
    print(f"  Limite de dias: {args.limite_dias or 'todos'}")

    conn_erp = conectar_erp()
    try:
        with engine().connect() as conn_local:
            estatisticas = carregar_pedidos(
                conn_erp,
                conn_local,
                limite_dias=args.limite_dias,
            )
    finally:
        conn_erp.close()

    print()
    print("=== Resultado da carga ===")
    print(f"  Pedidos lidos do ERP: {estatisticas['pedidos_lidos']}")
    print(f"  Pedidos inseridos: {estatisticas['pedidos_inseridos']}")
    print(f"  Pedidos atualizados: {estatisticas['pedidos_atualizados']}")
    print(f"  Itens inseridos: {estatisticas['itens_inseridos']}")
    print(f"  Itens atualizados: {estatisticas['itens_atualizados']}")
    if estatisticas["erros"]:
        print(f"  Erros: {len(estatisticas['erros'])}")
        for e in estatisticas["erros"]:
            print(f"    - {e}")
    print("Carga concluída com sucesso.")


if __name__ == "__main__":
    main()
