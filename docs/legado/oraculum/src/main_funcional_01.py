from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from database import get_connection
import pyodbc
from typing import List
from io import BytesIO
import tempfile

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
from reportlab.lib import colors


app = FastAPI()


@app.get("/dados", summary="Consulta CTE_Peca + joins")
def get_dados():
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT
        CP.Lote_Interno, 
        CP.Aviso,
        CP.Gaveta,
        CP.SubLote,
        CP.Situacao,
        CP.Nro_Rolo,
        CP.Nro_Peca,
        CP.Produto,
        CP.Categoria,
        CP.Categoria_Tinto,
        CP.Cor,
        CP.Desenho,
        CP.Variante,
        CP.Largura,
        CAST(CP.Metros AS DECIMAL(18,2)) AS Metros,
        CAST(CP.Peso AS DECIMAL(18,2)) AS Peso,
        CP.Tear AS Rolo_Packlist, 
        CP.Data_Entrada,
        (CP.Nro_Rolo + CP.Situacao + CP.Cor + CP.Desenho) AS Chave, 
        PT.Linha
    FROM DBMicrodata_DGB.dbo.Cte_Peca CP 
    LEFT JOIN DBMicrodata_DGB.dbo.CTE_Baixa CB 
        ON (CP.Empresa = CB.Empresa 
            AND CP.Situacao = CB.Situacao 
            AND CP.Nro_Rolo = CB.Nro_Rolo 
            AND CP.Nro_Peca = CB.Nro_Peca) 
    LEFT JOIN DBMicrodata_DGB.dbo.Produtos_Tecidos PT 
        ON (CP.EmpProd = PT.Empresa 
            AND CP.Produto = PT.Produto) 
    WHERE CP.Nro_Rolo_Origem IS NULL 
        AND CB.Empresa IS NULL 
    ORDER BY
        CP.SubLote ASC,
        CP.Tear ASC,
        CP.Gaveta ASC,
        CP.Produto ASC,
        CP.Cor ASC,
        CP.Aviso DESC,		
        CP.Nro_Rolo DESC,		
        CP.Categoria_Tinto ASC
    """

    cursor.execute(query)
    columns = [col[0] for col in cursor.description]
    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return results


@app.get("/sugestao-rolos/{pedido}", summary="Executa procedure de sugestão de rolos")
def sugestao_rolos(pedido: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("EXEC uspEnderecamentoParaAtenderPedidoGeral ?", pedido)

        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/pdf/sugestao-rolos/{pedido}", summary="Gera PDF em formato de cartões lado a lado")
def gerar_pdf_cartoes(pedido: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("EXEC uspEnderecamentoParaAtenderPedidoGeral ?", pedido)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]

        if not rows:
            return JSONResponse(status_code=404, content={"erro": "Nenhum item encontrado"})

        dados = [dict(zip(columns, row)) for row in rows]

        # Criação do PDF temporário
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        doc = SimpleDocTemplate(
            temp_file.name,
            pagesize=landscape(A4),
            rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20
        )

        elements = []
        row_cards = []
        card_count = 0
        max_cards_per_row = 3  # ajustável conforme largura desejada

        for item in dados:
            card_data = [
                ["Produto", item.get("Produto", "")],
                ["Cor", item.get("Cor", "")],
                ["Qtde Item", item.get("Qtde_Item", "")],
                ["Qtde Saldo", item.get("Qtde_Saldo", "")],
                ["SubLote", item.get("Sublote", "")],
                ["Gavetas", item.get("Gavetas", "")],
                ["Qtde Peças", item.get("Qtde_Pecas", "")],
                ["Rolos", item.get("Rolos", "")],
                ["Total Metros", item.get("Total_Metros", "")]
            ]

            card = Table(card_data, colWidths=[80, 100])
            card.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]))

            row_cards.append(card)
            card_count += 1

            if card_count % max_cards_per_row == 0:
                elements.append(Table([row_cards], colWidths=[250] * max_cards_per_row, hAlign='LEFT'))
                elements.append(Spacer(1, 10))
                row_cards = []

        if row_cards:
            elements.append(Table([row_cards], colWidths=[250] * len(row_cards), hAlign='LEFT'))

        doc.build(elements)

        return StreamingResponse(
            open(temp_file.name, "rb"),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=sugestao_{pedido}.pdf"}
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"erro": "Erro ao gerar PDF", "detalhes": str(e)}
        )


# (Opcional, se quiser manter a função auxiliar de quebra de linha)
def quebra_linha(texto, largura_maxima, tamanho_medio_char=5):
    max_chars = int(largura_maxima / tamanho_medio_char)
    palavras = texto.split(" ")
    linhas = []
    linha = ""
    for palavra in palavras:
        if len(linha + " " + palavra) <= max_chars:
            linha += " " + palavra if linha else palavra
        else:
            linhas.append(linha)
            linha = palavra
    if linha:
        linhas.append(linha)
    return linhas
