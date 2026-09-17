ALTER PROCEDURE uspEnderecamentoParaAtenderPedidoGeral
    @Pedido char(8)
AS
BEGIN
    SET NOCOUNT ON;

/*
Autor: Tiago de Abreu
Data: 01/07/2025
*/
    -- Tabela com os itens do pedido
    DECLARE @Itens TABLE (
        Produto VARCHAR(30),
        Cor VARCHAR(10),
        Qtde_Saldo DECIMAL(18,4)
    );

    INSERT INTO @Itens (Produto, Cor, Qtde_Saldo)
    SELECT Produto, Cor, Qtde_Saldo
    FROM DBMicrodata_DGB.dbo.Vw_Car_Itens_Pedido
    WHERE Pedido = @Pedido;

    -- Tabela temporária para armazenar o resultado final
    CREATE TABLE #Resultado (
        Produto VARCHAR(30),
        Cor VARCHAR(10),
        Qtde_Item DECIMAL(18,4),
        Qtde_Saldo DECIMAL(18,4),
        Sublote VARCHAR(20),
        Gavetas NVARCHAR(MAX),
        Rolos NVARCHAR(MAX),
        Qtde_Pecas INT,
        Total_Metros DECIMAL(18,4)
    );

    DECLARE @Produto VARCHAR(30), @Cor VARCHAR(10), @Saldo DECIMAL(18,4), @Qtde_Item DECIMAL(18,4);

    DECLARE item_cursor CURSOR FOR
        SELECT Produto, Cor, Qtde_Saldo FROM @Itens;

    OPEN item_cursor;
    FETCH NEXT FROM item_cursor INTO @Produto, @Cor, @Saldo;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        -- Recupera quantidade total do item do pedido
        SELECT TOP 1 @Qtde_Item = Qtde
        FROM DBMicrodata_DGB.dbo.Vw_Car_Itens_Pedido
        WHERE Pedido = @Pedido AND Produto = @Produto AND Cor = @Cor;
        -- Buscar rolos em estoque disponíveis para o item do pedido
        WITH RolosDisponiveis AS (
            SELECT 
                CP.Sublote,
                CP.Gaveta,
                CP.Nro_Rolo,
                CP.Nro_Peca,
                CP.Metros,
                CP.Produto,
                CP.Cor,
                ROW_NUMBER() OVER (ORDER BY CP.Gaveta, CP.Tear DESC, CP.Nro_Rolo DESC) AS RowNum
            FROM DBMicrodata_DGB.dbo.Cte_Peca CP
            LEFT JOIN DBMicrodata_DGB.dbo.CTE_Baixa CB 
                ON CP.Empresa = CB.Empresa 
                AND CP.Situacao = CB.Situacao 
                AND CP.Nro_Rolo = CB.Nro_Rolo 
                AND CP.Nro_Peca = CB.Nro_Peca
            WHERE 
                CP.Nro_Rolo_Origem IS NULL
                AND CB.Empresa IS NULL
                AND CP.Produto = @Produto
                AND CP.Cor = @Cor
        ),
        Acumulado AS (
            SELECT 
                *,
                SUM(Metros) OVER (ORDER BY RowNum) AS Soma_Metros
            FROM RolosDisponiveis
        ),
        Selecionados AS (
            SELECT * FROM Acumulado
            WHERE Soma_Metros <= @Saldo
               OR ABS(Soma_Metros - @Saldo) < 0.01
        )/*
        Selecionados AS (
		    SELECT TOP 100 P.*
		    FROM Acumulado P
		    WHERE Soma_Metros >= @Saldo
		    ORDER BY Soma_Metros
		)
		Selecionados AS (
		    SELECT * FROM Acumulado
		    WHERE Soma_Metros >= @Saldo 
		      AND Soma_Metros <= (@Saldo * 1.05)
		    ORDER BY Soma_Metros ASC
		)*/
        INSERT INTO #Resultado
        SELECT 
            @Produto AS Produto,
            @Cor AS Cor,
            @Qtde_Item AS Qtde_Item,
            @Saldo AS Qtde_Saldo,
            MIN(Sublote) AS Sublote,
            STUFF((SELECT ', ' + Gaveta FROM (
                      SELECT DISTINCT Gaveta FROM Selecionados
                  ) AS DistGavetas
                  FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, '') AS Gavetas,
            STUFF((SELECT ', ' + RIGHT('0000000000' + Nro_Rolo, 10) + RIGHT('000' + Nro_Peca, 3)
                   FROM Selecionados
                   ORDER BY Nro_Rolo, Nro_Peca
                   FOR XML PATH(''), TYPE).value('.', 'NVARCHAR(MAX)'), 1, 2, '') AS Rolos,
            COUNT(*) AS Qtde_Pecas,
            SUM(Metros) AS Total_Metros
        FROM Selecionados;

        FETCH NEXT FROM item_cursor INTO @Produto, @Cor, @Saldo;
    END

    CLOSE item_cursor;
    DEALLOCATE item_cursor;

    -- Exibir o resultado final
    SELECT * FROM #Resultado ORDER BY Produto, Cor;

    DROP TABLE #Resultado;
END;