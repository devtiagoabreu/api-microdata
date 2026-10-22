function getAPIEstoqueEmAberto() {

  const URL_API = 'http://94550ac37bb5.sn.mynetname.net:58244/dados';
  const NOME_ABA = 'ESTOQUE';

  // Campos que devem ser tratados como números
  const CAMPOS_NUMERICOS = new Set([
    'Largura',
    'Metros',
    'Peso'
  ]);

  // Evita duas execuções simultâneas
  const lock = LockService.getScriptLock();

  if (!lock.tryLock(1000)) {
    Logger.log('Já existe uma atualização em andamento.');
    return;
  }

  const inicio = Date.now();

  try {

    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = spreadsheet.getSheetByName(NOME_ABA);

    if (!sheet) {
      throw new Error(`A aba "${NOME_ABA}" não existe.`);
    }


    // =====================================================
    // 1. CONSULTA A API
    // =====================================================

    const response = UrlFetchApp.fetch(URL_API, {
      method: 'get',
      muteHttpExceptions: true
    });

    const status = response.getResponseCode();

    if (status !== 200) {
      throw new Error(`Erro na API. HTTP ${status}`);
    }

    const texto = response.getContentText();

    if (!texto) {
      throw new Error('A API retornou resposta vazia.');
    }

    const data = JSON.parse(texto);


    // =====================================================
    // 2. VALIDA O RETORNO
    // =====================================================

    if (!Array.isArray(data)) {
      throw new Error('O retorno da API não é um array.');
    }

    if (data.length === 0) {
      Logger.log(
        'API retornou 0 registros. Planilha não alterada.'
      );
      return;
    }


    // =====================================================
    // 3. CABEÇALHOS
    // =====================================================

    const headers = Object.keys(data[0]);

    const qtdLinhas = data.length;
    const qtdColunas = headers.length;


    // =====================================================
    // 4. MONTA OS DADOS EM MEMÓRIA
    // =====================================================

    const values = new Array(qtdLinhas);

    for (let i = 0; i < qtdLinhas; i++) {

      const row = data[i];
      const linha = new Array(qtdColunas);

      for (let j = 0; j < qtdColunas; j++) {

        const header = headers[j];
        const valor = row[header];

        // -----------------------------------------------
        // Campos numéricos
        // -----------------------------------------------

        if (CAMPOS_NUMERICOS.has(header)) {

          if (
            valor === null ||
            valor === undefined ||
            valor === ''
          ) {
            linha[j] = '';
            continue;
          }

          if (typeof valor === 'number') {

            linha[j] = Number.isFinite(valor)
              ? valor
              : '';

            continue;
          }

          let textoValor = String(valor).trim();

          // Trata 1.234,56
          if (
            textoValor.includes('.') &&
            textoValor.includes(',')
          ) {
            textoValor = textoValor
              .replace(/\./g, '')
              .replace(',', '.');

          // Trata 1234,56
          } else if (textoValor.includes(',')) {
            textoValor = textoValor.replace(',', '.');
          }

          const numero = Number(textoValor);

          linha[j] = Number.isFinite(numero)
            ? numero
            : '';

        } else {

          // -----------------------------------------------
          // Campos texto
          // -----------------------------------------------

          linha[j] =
            valor === null ||
            valor === undefined
              ? ''
              : String(valor);
        }
      }

      values[i] = linha;
    }


    // =====================================================
    // 5. GARANTE ESPAÇO NA PLANILHA
    // =====================================================

    const linhasNecessarias = qtdLinhas + 1;

    if (sheet.getMaxRows() < linhasNecessarias) {

      sheet.insertRowsAfter(
        sheet.getMaxRows(),
        linhasNecessarias - sheet.getMaxRows()
      );
    }

    if (sheet.getMaxColumns() < qtdColunas) {

      sheet.insertColumnsAfter(
        sheet.getMaxColumns(),
        qtdColunas - sheet.getMaxColumns()
      );
    }


    // =====================================================
    // 6. LIMPA OS DADOS ANTIGOS
    // =====================================================

    const ultimaLinha = sheet.getLastRow();
    const ultimaColuna = sheet.getLastColumn();

    if (ultimaLinha > 1) {

      sheet
        .getRange(
          2,
          1,
          ultimaLinha - 1,
          Math.max(ultimaColuna, qtdColunas)
        )
        .clearContent();
    }


    // =====================================================
    // 7. ESCREVE CABEÇALHO
    // =====================================================

    sheet
      .getRange(1, 1, 1, qtdColunas)
      .setValues([headers]);


    // =====================================================
    // 8. ESCREVE TODOS OS DADOS DE UMA VEZ
    // =====================================================

    sheet
      .getRange(2, 1, qtdLinhas, qtdColunas)
      .setValues(values);


    // =====================================================
    // 9. FORMATA TODAS AS COLUNAS DE UMA VEZ
    // =====================================================

    const formatosColunas = headers.map(header =>
      CAMPOS_NUMERICOS.has(header)
        ? '0.00'
        : '@'
    );

    const formatos = Array.from(
      { length: qtdLinhas },
      () => formatosColunas
    );

    sheet
      .getRange(2, 1, qtdLinhas, qtdColunas)
      .setNumberFormats(formatos);


    // =====================================================
    // 10. CONGELA O CABEÇALHO
    // =====================================================

    sheet.setFrozenRows(1);


    // =====================================================
    // 11. LOG
    // =====================================================

    const segundos =
      ((Date.now() - inicio) / 1000).toFixed(2);

    Logger.log(
      `Estoque atualizado: ${qtdLinhas} registros | ` +
      `${qtdColunas} colunas | ` +
      `${segundos}s`
    );

  } catch (erro) {

    Logger.log(
      `ERRO ao atualizar estoque: ${erro.message}`
    );

    throw erro;

  } finally {

    lock.releaseLock();
  }
}