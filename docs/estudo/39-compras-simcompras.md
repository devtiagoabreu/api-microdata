# Estudo 39 — Compras / SIMCompras (`Cmt_*`, `CMT_*`)

> **Data:** 18/set/2026
> **Escopo:** Módulo **SIMCompras Têxtil** — necessidade de compra, cotação, pedido de compra, entregas, aprovação, integração com aviso de recebimento (SIMRet) e geração de estoque.
> **Restrições:** apenas leitura; sem objetos novos em produção.
> **Relações:** Estudo 37 (SIMRet/aviso) e Estudo 38 (COMEX/custo de importação).

---

## 1. Identidade do módulo

`Sistema_Parametros = 'SIMCompras Têxtil'` em `Cmt_Parametros` (1 linha). 59 tabelas no prefixo (`Cmt_/CMT_`):
- **36 com dados** e **23 vazias** (itens de parametrização, fornecedores homologados, grupos de fornecedores, custo financeiro/importação, mensagens, CFOP embalagem, cotação DRP).
- **58 procedures `SP_[C]M`T_*`** (Cmt/CMT) + integração com SIMRet (`Ret_EnviaPedidoCompra*`).

Núcleo vivo (2018–2026, forte atividade 2021–2026, empresa **13**) é o **pedido de compra de importação de tecido/fio**.

---

## 2. Visão do fluxo

```
 Necessidade → Cotação → Pedido → Entrega(s) → [SIMRet] Aviso → Recebimento → Estoque
 (solicitação)  (cota p/    (aprovado)   (embarque/    (NF forne-   (SP_CMT_     (CTE_Peca,
                 forneced-                chegada/      cedor +      GeraEstoque  Ret_Lancamentos,
                 ores)                    entrega)     DI/dólar)    → entradas   fios…)
                                                                   livro/estoque)
```

---

## 3. Necessidade (solicitação de compra)

| Tabela | Linhas | Chave |
|--------|--------|-------|
| `Cmt_Necessidade` | 2 | `Empresa + Codigo` |
| `Cmt_Necess_Itens` | 2 | `+ Item` |
| `Cmt_Necess_Itens_Entrega` | 3 | `+ ID_Ent` |
| `Cmt_Necess_Itens_Entrega_Obs` | 3 | |
| `Cmt_Necess_Itens_Obs` | 2 | |
| `Cmt_Necessidade_Obs` | 1 | |
| `CMT_Necess_CCusto_*` | 2/2 | rateio centro de custo |

Colunas: `Empresa, Codigo, Data, Solicitante, Gerente, Tipo (01 TECIDO / 02 FIO), Data_Hora, Cancelado, Incluindo, requisicao, Aprovador_Sol, Origem`; itens com `EmpProd→Produto`, `Cor`, `Qtde`, `Situacao/Desenho/Variante/Categoria`.

- Numeração por empresa em `Cmt_ParamEmp.Ult_Necess` (emp 13 = `'6'`).
- Geração da cotação a partir da necessidade: `SP_Cmt_GeraCotacao (@Empresa, @Necessidade, @Cotacao OUTPUT)` → cria `Cmt_Cotacao`.
- Geração direta de pedido a partir de solicitação: `SP_Cmt_GerarPedidoSC (@Empresa, @Necessidade, @Pedido OUTPUT)`.

---

## 4. Cotação (`Cmt_Cotacao*`)

| Tabela | Linhas | Conteúdo |
|--------|--------|----------|
| `Cmt_Cotacao` | 2 | Cabeçalho (2 cotação, emp 13, status `G`, `Liberado=S`, 1 de cada tipo) |
| `Cmt_Cotacao_Prod` | 2 | Produtos cotados por solicitação (`Solicitacao`, `Aprovado`, `Cancelado`, `Pedido_Urgente`) |
| `Cmt_Cotacao_Itens` | 4 | Oferta por fornecedor (`Fornecedor`, `Vr_Unitario`, `Vr_Custo`, `Selecionado=N`) |
| `Cmt_Cotacao_Itens_Entrega` | 6 | Entregas da oferta (`Data_Entrega`, `Qtde`, `ID_Ent`) |
| `Cmt_Cotacao_Obs` / `_Prod_Obs` | 2 / 2 | Observações |
| `Cmt_Cotacao_Solicit` | 2 | Vínculo cotação ↔ solicitação/necessidade |
| `CMT_Cotacao_CCusto_*` | 2 / 2 | Rateio centro de custo da cotação |

Campos-chave do item (`Cmt_Cotacao_Itens`): `Item_Prod` (nº produto na cotação), `Item` (nº oferta do fornecedor), `Fornecedor`, `Qtde`, `Vr_Unitario`, `Vr_Custo` (**usado p/ pedido** ≈ valor com encargos), `ICMS/IPI` (homologação de fornecedor), `Vr_Encargo`, `Marca/Garantia`, `Frete_Trans`, `Cond_Pagto_Digitavel`, `Selecionado`, `Vr_Unitario2`, `Vr_Moeda_Estrangeira`, `Qtde_Compra`/`Vr_Unitario_Compra`.

- Geração: `SP_Cmt_Start_Cotacao` (a partir de solicitação); `SP_Cmt_GeraCotacao` (cria cotação de necessidade); homologação de fornecedores; **envio ao fornecedor** por e-mail: `SP_Cmt_EnvioCotacao`.
- Cruzamento de cotações de fornecedores: `SP_Cmt_UltimasCotacao`, `SP_Cmt_RelCotacao`, `SP_Cmt_RelCotacao_ItenForn`.

---

## 5. Pedido de compra (`Cmt_Pedido*`) — núcleo

| Tabela | Linhas | Chave |
|--------|--------|-------|
| `Cmt_Pedido` | 228 | `Empresa + Pedido` |
| `Cmt_Pedido_Itens` | 2.171 | `+ Item` |
| `Cmt_Pedido_Itens_Entrega` | 2.172 | `+ ID_Ent` (1..3, 1 típico) |
| `Cmt_Pedido_Itens_Entrega_Log` | 5 | auditoria de alteração de entregas |
| `Cmt_Pedido_Itens_Entrega_Obs` | 1 | |
| `Cmt_Pedido_Itens_Obs` | 644 | observações por item |
| `Cmt_Pedido_Obs` | 3 | observações do pedido |
| `Cmt_Pedido_Itens_Cotacao` | 0 | (vazio; usado só durante geração) |
| `Cmt_Pedido_CCusto_*` | 0 | rateio por centro de custo (não usado hoje) |

### 5.1 `Cmt_Pedido` (cabecalho)

`Empresa, Pedido, Tipo_Fornec, Fornecedor, Data, Data_Hora, Transportadora, Redespacho, Frete_Trans, Frete_Redes, Vr_Pedido, Comprador, Tipo, Cond_Pagto_extenso, Aprovado_Valor, Diretor, Reprovado_Diretor, Data_Visto_Diretor, Enviado_Fornecedor, Reprovado_Valor, Aprovacao_Valor_Manual, Favorecido, PedidoFornecedor, Vlr_Frete, Data_Entrega, Data_Producao, Data_Embarque, solicitacao, Vr_Desconto, porc_Desconto, Codigo_Moeda, Data_Cambio, Data_Cambio_Atualizacao, Cond_Pagto, Ult_Atualizacao, Canal, IdLocalDesembaraco, IDContratoGrupoFornecedor, Contrato, TipoComerc, Data_Desembarque`.

FK: `Fornecedor→Clientes_Principal`, `Empresa→Empresas`, `Transportadora/Redespacho→Transportadoras`, `Codigo_Moeda→Ret_Moedas`, `Cond_Pagto→Condicoes_Pagto`, `IDContratoGrupoFornecedor→Cmt_Grupo_Fornecedores`, `TipoComerc→Fig_Comercializacao`.

Estado no dataset:
- `Empresa`: 227× `13` + 1× `01`; `Tipo='01'` (TECIDO) em todos os 228.
- `Codigo_Moeda='02'` (dólar) em 223; `'01'` real em 1; NULL em 4. `Data_Cambio` **NULL em todos** (câmbio aplicado só no custo/entrada).
- `Aprovado_Valor='S'` (228), `Reprovado_Diretor='N'` (228, nenhum reprovado), `Enviado_Fornecedor='S'` em 91 / `'N'` em 137.
- `PedidoFornecedor` preenchido 100% (número do pedido no fornecedor); `Data_Embarque`/`Data_Desembarque` presentes (importação marítima).
- `Frete_Trans='1'` (194) vs `'0'` (34) — FOB/CIF por transporte.

Volumes anuais (emp 13, `Vr_Pedido`): 2018: R$ 216 mil (1) · 2021: R$ 793 mil (13) · 2022: R$ 1,49 mi (26) · 2023: R$ 1,96 mi (39) · 2024: R$ 2,75 mi (56) · 2025: R$ 2,61 mi (56) · 2026: R$ 1,71 mi (36) · **Σ ≈ R$ 11,5 mi em 228 pedidos**.

Fornecedores principais: **P2B TRADING MANAGEMENT INC** (00146, 143 pedidos — importação via trading das Ilhas Virgens), ZHEJIANG HAOYUE TEXTILE (00113, 31), ZHEJIANG WOWTIDE (00089, 30), HAINING HUAYI (00079, 13), etc. — praticamente todos **têxteis chineses** (ver Estudo 38).

### 5.2 `Cmt_Pedido_Itens`

`Empresa, Pedido, Item, EmpProd, Produto, Cor, Qtde, Vr_Unitario, Vr_Total, ICMS, IPI, Garantia, Marca, Cotacao, Vr_Unitario2, Categoria, Desenho, Variante, Situacao, Vr_Desconto, porc_Desconto, Fk_PCP_Acondicionamento, Qtde_Compra, Vr_Moeda_Estrangeira, Vr_Unitario_Compra, metros, peso, Codigo_Concatenado, Ult_Atualizacao, QtdeVolumes, Peso_Bruto, PIS, COFINS`.

Regras observadas:
- **20 produtos** (EmpProd `01`), **66 cores**, 195 combinações produto+cor, 2.171 itens; `Situacao='001'` (2170) / `'000'` (1); `Categoria='01'`.
- `Vr_Total = Qtde × Vr_Unitario` (verificado com ROUND 2 — conferido em pedido 000005).
- `Qtde_Compra`/`Vr_Unitario_Compra` = Qtde/unitário **na unidade de compra** (QMP — via `Ret_Unidades`); `Vr_Moeda_Estrangeira`/`Vr_Unitario2` = valores na moeda do fornecedor.
- Top produtos por nº de itens: `000020` (735 itens / 5,1 mi m / R$ 2,93 mi), `000015` (464), `000014` (413), `000013` (144), `000019` (108).

### 5.3 `Cmt_Pedido_Itens_Entrega` (programação de embarque)

`Empresa, Pedido, Item, ID_Ent, Data_Entrega, Qtde, Qtde_Recebida, Qtde_Acerto, Qtde_Compra, Qtde_Recebida_Compra, Qtde_Acerto_Compra, DataPrevEmbarque, DataPrevPorto`.

- 1 entrega típica (`ID_Ent=1`); até 3. `DataPrevEmbarque`/`DataPrevPorto` preenchidos em **2.148/2.172** (importação: prevêem embarque marítimo e chegada ao porto).
- `Qtde` (unidade produto) vs `Qtde_Compra` (unidade compra) — preenchidos; `Qtde_Recebida` = quantidade recebida via SIMRet.
- Auditoria: `Cmt_Pedido_Itens_Entrega_Log` (registra inserções/alterações com usuário e observação).

---

## 6. Geração do pedido (`SP_Cmt_GeraPedido`)

`SP_Cmt_GeraPedido (@Empresa, @Cotacao_Urg, @PedInicial OUTPUT, @PedFinal OUTPUT, @CotaCoesSel, @PedAuto='N')` (40 KB; criada 30/06/2010, atualizada 23/07/2024):

1. Carrega itens de `Cmt_Cotacao_Itens` selecionados (`#TMP_PEDFOR`);
2. Define `Codigo_Moeda`, conversão de medida/moeda (`Ret_ParamEmp.Empresa` do `Liv_Diario` → `Empresa_Produtos`);
3. **INSERT `cmt_pedido`** (cabeçalho) com `Empresa, Pedido (seq via Cmt_ParamEmp.Ult_Pedido), Fornecedor, Condicao..., Vr_Pedido, ...`;
4. **INSERT `cmt_pedido_itens`** (a partir do item de cotação: produto/cor/situação/vr unitário/encargos), `cmt_pedido_itens_obs`, `Cmt_Pedido_Itens_Cotacao`;
5. **INSERT `cmt_pedido_itens_Entrega`** (agrupando entregas do fornecedor) e `_Entrega_Obs`; `cmt_pedido_CCusto_*` se CC na cotação;
6. Recalcula `Vr_Pedido`, define `Aprovado_Valor` (aprovação financeira), grava `Diretor`/`Data_Visto_Diretor` quando `Diretor`=Gerente;
7. Marca `Cmt_Cotacao.Status='P'` (processada) e `Cmt_Cotacao_Prod.Pedido_Urgente`.

Fluxos de baixo nível:
- `SP_Cmt_Insert_ItensPedido` — insere itens de pedido a partir de aviso/entrega.
- `SP_Cmt_Insert_ItensEntrega` e `SP_CMT_CarregaInfo_ItensPedido` — entregas (dados corretos das entregas p/ tela de pedido).
- `SP_CMT_ValidaFiltroProd` — filtro produto/grade.
- **Critica**: `SP_Cmt_CriticaGeraPedido` (agrupa cotação: mesmo produto+fornecedor+valor+condição de pagamento) e `SP_Cmt_Critica_Pedido` (regras de validade), `SP_Cmt_Ped_Valor_Excedente`.
- **Aprovação**: `SP_Cmt_Aprovacao_DiretorGerente` (aprova quando diretor = gerente; usa `Cmt_Parametros.Usar_Mesmo_GerenteDiretor`).
- **Reajuste/câmbio**: `SP_Cmt_Recalcula_Cambio` (recálculo de câmbio), `SP_CMT_PREENCHER_VR_UNITARIO_EFETIVO`.
- **Cópia**: `SP_CMT_CopiaPedido`, `SP_Copia_Pedido`.
- **Manutenção de entregas**: `SP_CMT_CALCULA_VECTO_ENTREGA` (vencimentos escalonados de entrega).

---

## 7. Integração com SIMRet / aviso de recebimento

- Pedido é **atendido pelo aviso**: `Ret_Aviso_Itens_Pedido_Atend` (2.083 linhas, 217 pedidos 1:1; view `vw_Ret_Aviso_Itens_Pedido_Atend`) — Estudo 37.
- Envio do pedido de compra ao fornecedor: `Enviado_Fornecedor`.
- **Geração de estoque** na entrada (`SP_CMT_GeraEstoque @Empresa, @Aviso`, 37 KB; atualizada 15/05/2024 com "lote do fornecedor"):
  Cria/atualiza `Cte_Peca`, `Cfc_Pecas`, `Ret_Lancamentos`, `Cfc_Ret_Lancamentos`, `Ret_CxsFios`, `Fio_Fardos` e `Ret_Itens_Lote`; zera/gera caixas de fios. Preço unitário efetivo via `SP_CMT_PREENCHER_VR_UNITARIO_EFETIVO` e impostos conforme `CompoeCalculo`.
- **Valorização do estoque** recebido: `SP_CMT_ValorizacaoEstoque` (12/08/2019; filtros por processo, produto; `SomenteMoeda1/2`), usada pelo painel de custo.
- **Saldo em aberto**: `SP_CMT_Calcula_SaldoEmAberto` (Avisos/pedidos/itens) → tabela `CMT_SaldosEmAberto` (108 linhas na data do estudo: saldos futuros de `Veludo Confort` 01.00014 etc.) — ver §9.

---

## 8. Configuração e parametrização

| Tabela | Linhas | Conteúdo |
|--------|--------|----------|
| `Cmt_Parametros` | 1 | `Integra_Pagar=S`, `Usar_Aprovacao_Pedido=N`, `Valor_Aprovacao_Pedido=0`, `Usar_Aprovacao_Pedido_Direto=N`, `Usar_Mesmo_GerenteDiretor=N`, `Processos_Pendentes_Empresa=N`, **`Usar_Aviso_Pedido=S`**, `Toler_VrUnit_Aviso=0`, `Toler_Qtde_Aviso=0`, `GeraItensCotacao_Forn=S`, `GeraItensCotacao_Aut=S`, `Encargos_Mes=0` |
| `Cmt_ParamEmp` | 5 | emp 13: `Ult_Necess=6`, `Ult_Cotacao=000002`, `Ult_Pedido=000276`, `ult_requisicao=1`, `ult_requisicao_itens=2`, `CarregaUltPrecoProdPedAnt=S`, `EstoqueEntradaCompras=R`, `Incremento_rolo=50`, `Usar_dataEmbarque_DataProducao=S` |
| `Cmt_ParamEmp_SecaoRequisicao` | 1 | emp 13 → Secao `001` |
| `Cmt_Tipo_Pedido` | 2 | `01 TECIDO` (Usa_SCD, campos Situacao/Cor/Desenho/Variante/Categoria) · `02 FIO` (Usar_Cor); ambos `Importacao=S` |
| `Cmt_Mensagens` | 0 | rodapé e-mail de cotação (desativado) |
| `CMT_FornecedorHomologado(_Produto)` | 0 | homologação de fornecedor por produto (desativado no momento) |
| `Cmt_Grupo_Fornecedores(_Empresas)` | 0 | grupos/contratos (FK de `Cmt_Pedido.IDContratoGrupoFornecedor`, vazio) |
| `CMT_Condicoes_Pagto` | 1 | empId 4 → condição `0G` |
| `CMT_LocalDesembaraco` | 2 | 1=ITAJAI, 2=NAVEGANTES (marítimo) |
| `CMT_QtdeEstoque_AvisosNFinalizados` | 0 | (scratch para relatório) |
| `CMT_TipoCusto`, `CMT_CustoFinanceiro`, `CMT_FluxoPagto`, `CMT_PedidoCustoImport` | 0 | custo financeiro/importação (desativado; Estudo 38) |

---

## 9. Views e consultas de apoio

- `VW_CMT_PedidoCompra_Itens`, `VW_CMT_Pedido_Itens_Entrega`, `VW_CMT_RelCompras`, `VW_CMT_RelConsumo`, `VW_CMT_Status_Item_Cotacao`.
- `vw_Cmt_Necessidade_Produto_Aberto`, `vw_Cmt_Necess_itens_entrega_Aberto`, `vw_cmt_Pedido_Itens_Entrega_Aberto`, `Vw_Cmt_Saldo_Pedidos`, `Vw_Cmt_Requisicao_baixa`.
- `SP_Cmt_Rel*` (relatórios): `RelPedido`, `RelPedidoAberto`, `Rel_Pedido_Recebidos`, `RelPedido_EndEntrega`, `RelCotacao`, `RelSolicitacao`, `Rel_Requisicao*`, `Rel_PedidoAberto`.
- Pesquisa de **preço/consumo histórico** (usada p/ sugerir valores): `SP_Cmt_UltimasCompras`, `SP_Cmt_UltimosPedido`, `SP_Cmt_UltimosConsumo`, `SP_Cmt_UltimasCotacao`.

---

## 10. Observações para a nova API

1. **Fonte de verdade do pedido de compra** = `Cmt_Pedido` + `Cmt_Pedido_Itens` + `Cmt_Pedido_Itens_Entrega`. Itens de entrega são independentes de aviso (Qtde_Recebida preenchido pelo SIMRet).
2. **Moeda**: `Codigo_Moeda='02'` = dólar; `Vr_Pedido` está **na moeda do pedido** (verificar com câmbio da data). `Vr_Moeda_Estrangeira`/`Vr_Unitario_Compra` no item.
3. **Número do pedido**: `Cmt_ParamEmp.Ult_Pedido` é o comando já consumido (última seq). Para a API: usar `Cmt_Pedido.Pedido` como PK; montar prefixo por empresa na leitura relacional.
4. **Centro de custo** e **homologação de fornecedor** (tabelas vazias) — ignorar para o contrato atual; reavaliar quando incluírem o módulo completo (atualmente pedidos não usam CC).
5. **Relação com NF/estoque**: entrada de mercadoria = `Ret_Lancamentos`/`Liv_Entradas` (gerado por `SP_CMT_GeraEstoque`/`Ret_Lanca_Entradas`); não nasce direto do pedido. Para "entregas recebidas do pedido" usar `Cmt_Pedido_Itens_Entrega.Qtde_Recebida( _Compra)`.
6. **Saldo em aberto**: `SP_CMT_Calcula_SaldoEmAberto` **recalcula sob demanda** → nova API deve reproduzir a query de `#TMP_SaldoEmAberto` (aviso+atendimento, pedidos, `QtdeEstoque` por QMP). Sem valor persistido confiável (`CMT_SaldosEmAberto` é snapshot do último Run).
7. **Status legível**: pedido ≈ `Aprovado_Valor/Diretor/Reprovado_Diretor/Enviado_Fornecedor`; cotação ≈ `Status (G gerada/P processada)/Liberado/Aprovado`.
8. **PKS sem `IDENTITY`** — chaves compostas `char`; atenção ao padding ao comparar com `Fat_Itens_Pedido_DI` (Pedido char(6)).
9. **Dois tipos** de pedido: TECIDO (grade SCD: Situacao/Cor/Desenho/Variante/Categoria) e FIO (Cor). Disponibilizar os campos de grade conforme `Cmt_Tipo_Pedido.Usa_SCD`.

---

## 11. Próximos passos

- Estudo 40 — aprofundar **contrato de saldo em aberto** (reproduzir a query da `SP_CMT_Calcula_SaldoEmAberto`) para o endpoint de "posição de pedidos de compra".
- Confirmar **regra de câmbio** na API (onde o dólar vira real em `Vr_Pedido`/custo) — `SP_Cmt_Recalcula_Cambio` + `Ret_Moedas(_Diario)`.
- Avaliar cobertura do legado `oraculum` → qual endpoint usa pedido de compra (nena: `main.py` não tem; validar).

---

_Fontes: pesquisa direta em `sys`/`INFORMATION_SCHEMA` + amostras das tabelas `Cmt_*`/`CMT_*`; definições salvas em `defs/SP_Cmt_GeraPedido.sql`, `SP_CMT_Calcula_SaldoEmAberto.sql`, `SP_CMT_GeraEstoque.sql`, `SP_CMT_ValorizacaoEstoque.sql`, `SP_Cmt_Start_Cotacao.sql`, `SP_Cmt_GeraCotacao.sql`, `SP_Cmt_CriticaGeraPedido.sql`, `SP_Cmt_Aprovacao_DiretorGerente.sql`, `SP_CMT_PreencheVr_UnitarioEfetivo.sql`, `SP_Cmt_EnvioCotacao.sql`, `SP_Cmt_GerarPedidoSC.sql`, `SP_CMT_CarregaInfo_ItensPedido.sql`._