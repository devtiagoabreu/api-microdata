from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from database import get_connection
import pyodbc
from typing import List, Optional
from io import BytesIO
import tempfile
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
from reportlab.lib import colors

app = FastAPI()

# FUNÇÃO AUXILIAR PARA CONVERTER DATA
def formatar_data_para_sql(data_str: str) -> str:
    """
    Converte data no formato '25122024' para '25/12/2024'
    """
    if len(data_str) == 8:
        dia = data_str[:2]
        mes = data_str[2:4]
        ano = data_str[4:]
        return f"{dia}/{mes}/{ano}"
    else:
        return data_str

# ENDPOINTS EXISTENTES (mantidos para DBMicrodata_DGB)
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
        CP.Num_Etq_Aux,
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

        cursor.execute("EXEC DBMicrodata_DGB.dbo.uspEnderecamentoParaAtenderPedidoGeral ?", pedido)

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
        cursor.execute("EXEC DBMicrodata_DGB.dbo.uspEnderecamentoParaAtenderPedidoGeral ?", pedido)
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
        max_cards_per_row = 3

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

# NOVOS ENDPOINTS COM BANCO DE DADOS CORRIGIDO (DBProDash)
@app.get("/faturamento/{data}", summary="Faturamento por data (formato: 25122024)")
def get_faturamento(data: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        data_formatada = formatar_data_para_sql(data)
        cursor.execute("EXEC DBProDash.dbo.uspFaturamento ?", data_formatada)
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/faturamento-dia/{data}", summary="Faturamento do dia (formato: 25122024)")
def get_faturamento_dia(data: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        data_formatada = formatar_data_para_sql(data)
        cursor.execute("EXEC DBProDash.dbo.uspFaturamentoDia ?", data_formatada)
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/contas-pagas/{data}", summary="Contas pagas por data (formato: 25122024)")
def get_contas_pagas(data: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        data_formatada = formatar_data_para_sql(data)
        cursor.execute("EXEC DBProDash.dbo.uspListagemBaixasPagar ?", data_formatada)
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/custos-administrativos-anual", summary="Custos administrativos anuais")
def get_custos_administrativos_anual():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Executa as procedures em sequência como no PHP
        cursor.execute("EXEC DBProDash.dbo.uspRel_CCusto_NiveisAnual")
        cursor.nextset()
        
        cursor.execute("EXEC DBProDash.dbo.uspCustoAdmArmFat")
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/custos-administrativos-mensal", summary="Custos administrativos mensais")
def get_custos_administrativos_mensal():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Executa as procedures em sequência como no PHP
        cursor.execute("EXEC DBProDash.dbo.uspRel_CCusto_NiveisMensal")
        cursor.nextset()
        
        cursor.execute("EXEC DBProDash.dbo.uspCustoAdmArmFatMensal")
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/descontos/{data}", summary="Descontos por data (formato: 25122024)")
def get_descontos(data: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        data_formatada = formatar_data_para_sql(data)
        cursor.execute("EXEC DBProDash.dbo.uspDesconto ?", data_formatada)
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/devolucoes/{data}", summary="Devoluções por data (formato: 25122024)")
def get_devolucoes(data: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        data_formatada = formatar_data_para_sql(data)
        cursor.execute("EXEC DBProDash.dbo.uspDevolucao ?", data_formatada)
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/estornos/{data}", summary="Estornos por data (formato: 25122024)")
def get_estornos(data: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        data_formatada = formatar_data_para_sql(data)
        cursor.execute("EXEC DBProDash.dbo.uspEstorno ?", data_formatada)
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/contas-receber-programado", summary="Contas a receber programado")
def get_contas_receber_programado():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("EXEC DBProDash.dbo.uspDashFinanceiroContasReceberProgramado")
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/contas-pagar-programado", summary="Contas a pagar programado")
def get_contas_pagar_programado():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("EXEC DBProDash.dbo.uspDashFinanceiroContasPagarProgramado")
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return results[0] if results else {}
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro no banco de dados: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ENDPOINT PARA DASHBOARD COMPLETO
@app.get("/dashboard-completo/{data}", summary="Todos os dados do dashboard (formato: 25122024)")
def get_dashboard_completo(data: str):
    try:
        data_formatada = formatar_data_para_sql(data)
        
        # Buscar todos os dados individualmente
        faturamento = get_faturamento(data)
        faturamento_dia = get_faturamento_dia(data)
        contas_pagas = get_contas_pagas(data)
        custos_anual = get_custos_administrativos_anual()
        custos_mensal = get_custos_administrativos_mensal()
        descontos = get_descontos(data)
        devolucoes = get_devolucoes(data)
        estornos = get_estornos(data)
        contas_receber = get_contas_receber_programado()
        contas_pagar = get_contas_pagar_programado()
        
        resultados = {
            "data_consulta": data_formatada,
            "faturamento": faturamento,
            "faturamento_dia": faturamento_dia,
            "contas_pagas": contas_pagas,
            "custos_administrativos_anual": custos_anual,
            "custos_administrativos_mensal": custos_mensal,
            "descontos": descontos,
            "devolucoes": devolucoes,
            "estornos": estornos,
            "contas_receber_programado": contas_receber,
            "contas_pagar_programado": contas_pagar
        }
        
        return resultados
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ENDPOINT DE HEALTH CHECK
@app.get("/health", summary="Health check da API")
def health_check():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 as status")
        result = cursor.fetchone()
        
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

# ENDPOINT PARA TESTE DE PROCEDURES
@app.get("/test-procedure/{procedure_name}", summary="Testa uma procedure específica")
def test_procedure(procedure_name: str, data: Optional[str] = None):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if data:
            data_formatada = formatar_data_para_sql(data)
            cursor.execute(f"EXEC DBProDash.dbo.{procedure_name} ?", data_formatada)
        else:
            cursor.execute(f"EXEC DBProDash.dbo.{procedure_name}")
        
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return {
            "procedure": procedure_name,
            "data_used": data_formatada if data else None,
            "results": results
        }
        
    except pyodbc.Error as e:
        raise HTTPException(status_code=500, detail=f"Erro na procedure {procedure_name}: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ENDPOINT PARA LISTAR PROCEDURES DISPONÍVEIS
@app.get("/procedures", summary="Lista todas as procedures disponíveis")
def get_procedures():
    procedures_dbprodasH = [
        "uspFaturamento",
        "uspFaturamentoDia",
        "uspListagemBaixasPagar", 
        "uspCustoAdmArmFat",
        "uspCustoAdmArmFatMensal",
        "uspDesconto",
        "uspDevolucao",
        "uspEstorno",
        "uspDashFinanceiroContasReceberProgramado",
        "uspDashFinanceiroContasPagarProgramado",
        "uspRel_CCusto_NiveisAnual",
        "uspRel_CCusto_NiveisMensal"
    ]
    
    procedures_dbmicrodata = [
        "uspEnderecamentoParaAtenderPedidoGeral"
    ]
    
    return {
        "DBProDash": procedures_dbprodasH,
        "DBMicrodata_DGB": procedures_dbmicrodata
    }

# FUNÇÃO AUXILIAR PARA QUEBRA DE LINHA
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

# MIDDLEWARE PARA CORS
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)