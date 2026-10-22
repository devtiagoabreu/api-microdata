/**
 * getAPIEstoqueEmAberto
 * -----------------------------------------------------------------------------
 * Coleta as peças de estoque em aberto na API nova (api-microdata) e joga na aba
 * ESTOQUE da planilha, que serve o Data Studio.
 *
 * O que mudou em relação ao script legado (que batia no oraculum:58244/dados):
 *
 *   1. A API nova exige login. O token sai de `POST /auth/login` (JSON {email, senha})
 *      e vai no header `Authorization: Bearer <token>` em todas as chamadas.
 *   2. A API nova é paginada: `/dados` devolve no máximo 10.000 peças por chamada.
 *      Aqui o script percorre as páginas com `offset` até vir uma página incompleta,
 *      então o resultado é a base completa (o legado devolvia tudo de uma vez).
 *   3. A baseURL, o email e a senha vêm preenchidos abaixo (usuário de serviço da
 *      api-microdata). Dá para sobrescrever sem editar o código pelas Propriedades
 *      do Script (Arquivo > Propriedades do projeto > Propriedades do script):
 *
 *        ESTOQUE_API_URL    ex.: http://SEU_HOST:58245
 *        ESTOQUE_API_EMAIL  ex.: usuario@empresa.com.br
 *        ESTOQUE_API_SENHA  (a senha)
 *
 * Os nomes das colunas de negócio não mudaram (Largura, Metros, Peso continuam
 * numéricos), então a formatação da planilha segue igual.
 *
 * Para trocar de aba/colunas, mexa só em NOME_ABA e CAMPOS_NUMERICOS.
 */

function getAPIEstoqueEmAberto() {

  // =====================================================
  // 0. CONFIGURAÇÃO
  // =====================================================

  const NOME_ABA = 'ESTOQUE';
  const TAMANHO_PAGINA = 10000; // teto da API nova (`limite` máx 10.000)

  // Usuário de serviço da api-microdata (mesmo das integrações do BI). O host é o
  // mesmo do legado, só na porta da API nova (58245).
  const URL_API_PADRAO = 'http://94550ac37bb5.sn.mynetname.net:58245';
  const EMAIL_PADRAO = 'bi@dgbcomex.com';
  const SENHA_PADRAO = 'ozxQ7Vq4L2KpWnR8';

  // Campos que devem ser tratados como números (nomes do retorno da API).
  const CAMPOS_NUMERICOS = new Set([
    'Largura',
    'Metros',
    'Peso'
  ]);

  // A Propriedade do Script, quando existir, tem prioridade sobre o valor padrão.
  const props = PropertiesService.getScriptProperties();
  const URL_API = (props.getProperty('ESTOQUE_API_URL') || URL_API_PADRAO).replace(/\/+$/, '');
  const EMAIL = props.getProperty('ESTOQUE_API_EMAIL') || EMAIL_PADRAO;
  const SENHA = props.getProperty('ESTOQUE_API_SENHA') || SENHA_PADRAO;

  // Evita duas execuções simultâneas
  const lock = LockService.getScriptLock();

  if (!lock.tryLock(1000)) {
    Logger.log('Já existe uma atualização em andamento.');
    return;
  }

  const inicio = Date.now();

  try {

    if (!URL_API || !EMAIL || !SENHA) {
      throw new Error(
        'Faltou URL, email ou senha da API. Verifique os valores padrão no ' +
        'topo do script ou as Propriedades do Script ' +
        '(ESTOQUE_API_URL, ESTOQUE_API_EMAIL, ESTOQUE_API_SENHA).'
      );
    }

    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = spreadsheet.getSheetByName(NOME_ABA);

    if (!sheet) {
      throw new Error(`A aba "${NOME_ABA}" não existe.`);
    }


    // =====================================================
    // 1. LOGIN (a API nova é falha fechada)
    // =====================================================

    const token = login(URL_API, EMAIL, SENHA);


    // =====================================================
    // 2. CONSULTA A API (paginada)
    // =====================================================

    const data = buscarTodasAsPecas(URL_API, token, TAMANHO_PAGINA);

    if (data.length === 0) {
      Logger.log('API retornou 0 registros. Planilha não alterada.');
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


/**
 * Troca email e senha por um JWT. Equivale ao login que o dgbcomex faz antes de
 * chamar a API (authConfig tipo "login": email/senha em JSON, token no campo `token`).
 */
function login(urlApi, email, senha) {

  const resposta = UrlFetchApp.fetch(`${urlApi}/auth/login`, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ email: email, senha: senha }),
    muteHttpExceptions: true
  });

  const status = resposta.getResponseCode();

  if (status !== 200) {
    throw new Error(`Falha no login. HTTP ${status}: ${resposta.getContentText()}`);
  }

  const corpo = JSON.parse(resposta.getContentText() || '{}');

  if (!corpo.token) {
    throw new Error('Login não retornou token.');
  }

  return corpo.token;
}


/**
 * Percorre `/dados` com `offset` até vir uma página incompleta.
 * A resposta é um array cru (uma peça por item), como no legado — só que em lotes.
 */
function buscarTodasAsPecas(urlApi, token, tamanhoPagina) {

  const todas = [];
  let offset = 0;

  while (true) {

    const url =
      `${urlApi}/dados?limite=${tamanhoPagina}&offset=${offset}`;

    const resposta = UrlFetchApp.fetch(url, {
      method: 'get',
      headers: { Authorization: `Bearer ${token}` },
      muteHttpExceptions: true
    });

    const status = resposta.getResponseCode();

    if (status !== 200) {
      throw new Error(
        `Erro na API /dados. HTTP ${status}: ${resposta.getContentText()}`
      );
    }

    const texto = resposta.getContentText();

    if (!texto) {
      throw new Error('A API retornou resposta vazia.');
    }

    const pagina = JSON.parse(texto);

    if (!Array.isArray(pagina)) {
      throw new Error('O retorno da API não é um array.');
    }

    todas.push.apply(todas, pagina);

    if (pagina.length < tamanhoPagina) {
      break;
    }

    offset += tamanhoPagina;
  }

  return todas;
}
