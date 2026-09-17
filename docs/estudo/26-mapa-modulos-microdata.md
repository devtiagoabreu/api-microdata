# Estudo 26 — Mapa de módulos da Microdata e sua relação no banco

Como o ERP Microdata organiza o banco por **módulos** (prefixos de tabela/procedure/view),
quais estão **em uso** nesta base (`DBMicrodata_DGB`) e o que cada um representa. Base para
decidir o que a nova API/Neon expõe.

## 1. Como o banco é organizado

- **5 003 tabelas** distribuídas em **253 prefixos** (`LEFT(name, 4)`) — cada prefixo é um
  **módulo/vertical** do ERP.
- O ERP é **multi-vertical**: traz o esqueleto de **todos** os segmentos que a Microdata atende;
  só uma fração tem dados.
- Convenção: `Prefixo_Tabela`, `Prefixo_Procedimento`, `VW_Prefixo_*` / `VW_...`, `SP_...`,
  funções `FNC_/fnc_`, triggers `TG_/tg_`, temporárias `#tmp_`.
- **Chaves**: `Empresa char(2)` + número `char` (padding à direita); campos `text` legados.
- Nem todo prefixo é módulo de negócio: há **infra** (`SIS`, `MIC`, `RPT`, `LOG`, `USUA`,
  `MAIL`, `XML`, `CONN`, `BKP`, `TMP`, `TPConflito`) e **customização do cliente** (`DGB`).

## 2. Módulos CORE (ERP base) — uso nesta base

| Módulo | Prefixos | Função | Uso (linhas) |
|--------|----------|--------|--------------|
| Sistema/parâmetros | `SIS`, `Sys` | Parâmetros globais, empresas, bancos de dados, usuário×empresa | 12 310 |
| Cadastros | `Clie`, `Enti`, `Empr`, `Cida`, `Esta`, `UF`, `Pais`, `Tran`, `Unid`, `Meio`, `Cart` | Clientes/entidades, empresas, cidades/UF/país, transportadoras, unidades, pagamento, cartões | 40 000+ |
| **Carteira/pedidos** | `Car` | Pedido → itens → romaneio → coleta → separação/despacho (Estudos 03–25) | **451 861** |
| **Faturamento/NF** | `Fat`, `Nota`, `NFE`, `NF` | Faturamento, notas fiscais, NFe, XML, histórico | **544 796** |
| **Contas a receber** | `Rec` | Duplicatas, comissões, carteira, CNAB recebimento | **590 037** |
| Contas a pagar | `Pag` | Títulos, baixas | 18 348 |
| Financeiro/tesouraria | `Bco`, `CH`, `Cheq`, `Cnab`, `Fin`, `FNN`, `Flux`, `Flu`, `CCD` | Bancos, cheques, CNAB, previsão/fluxo de caixa, cobrança (Estudo 23) | ~35 000 |
| Compras | `Cmp` | Compradores, pedidos de compra | 8 |
| **Estoque / peças** | `Cte`, `Inv`, `Inventario`, `EST`, `Lv3`, `LV3E` | `Cte_Peca` (rolos/peças), endereçamento/gavetas, inventário, saldos de fechamento | **1 047 070** |
| **Fiscal/SPED** | `Liv`, `Fig`, `Efd`, `Secf`, `Sped`, `Ciap`, `Copc`, `Copd`, `Livc`, `Mn`, `Mana`, `PAF` | Livros entrada/saída, grupos fiscais, EFD/ECF/CIAP, tabelas COP, MANAD, PAF-ECF | ~206 000 |
| Contabilidade | `Cont`, `Ctb*`, `Lanc` | Plano de contas/SPED, lançamentos (módulo **não mantido** — Estudo 23) | ~1 700 |
| **Custo** | `Custo`, `Mcg`, `Sct` | Custo industrial, custo por máquina/energia/GIF, custo médio (on-the-fly — Estudo 23) | ~1 (só params) |
| Beneficiamento/terceiros | `Ret` | Aviso de recebimento, facção, caixas de fios, importação | 4 497 |
| Follow-up | `Tipo`, `Sist`, `Peri`, `Regi`, `Ramo`, `Dias`, `Feri`, `Base` | Tabelas de apoio (tipos, periodicidade, regime, feriados) | pequenas |

## 3. Verticais (segmentos) — presença nesta base

| Vertical | Prefixo(s) | Função | Uso |
|----------|-----------|--------|-----|
| **Têxtil/confecção** | `PCP`, `Fio`, `Tnt`, `Plm`, `Cfc`, `Fab`, `Cmp` | PCP, fiação, **tinturaria** (`Tnt`), PLM, facção/confecção, ficha de corte | PCP 123; demais ≈0 |
| **Varejo/loja** | `Loj`, `PDV`, `SFC`, `Pdv`, `CFE`, `Orc` | Loja, PDV, ECF/Sintegra, cupom fiscal eletrônico, orçamento | ~30 |
| **Pneus** | `Pneu` | Revenda/serviços de pneus, garantia, EPneus | 40 |
| **Posto/combustível** | `PPR` | Motorista, combustível, prazos | 0 |
| **Adegas/vinhos** | `Adg` | Produtos, uva, sabor, especiaria | 1 |
| **Pré-moldados/obras** | `Prj` | Projetos, obras, protensões, traço de concreto | 17 |
| **Biblioteca** | `Bib` | Livros, empréstimos, multas | 27 |
| **Escola/curso** | `Alu` | Matrícula, disciplinas, notas, grade curricular | 1 |
| **Cestas/nutrição** | `Ces` | Pedido de cestas, nutricionista | 1 |
| **Fisioterapia** | `Unif` | Clínica/atendimento | 1 |
| **Alimentação/entrega** | `Exsped`, `Mix` | Expedição/esped, seleção mista | 0 |
| **CRM/marketing** | `Crm`, `Dir`, `Mala`, `Aten`, `Age`, `Mail`, `Reca` | CRM, mala direta, telemarketing, agenda, e-mail | ~14 100 |
| **Geradores de pedido** | `Gef`, `Glj`, `Grm`, `Gtf`, `Ven` | Variantes de entrada de pedido (venda normal / loja-cupom / transferência entre empresas) | ≈4 |

> Os verticais `PCP/Fio/Tnt/Plm/Cfc/Fab`, `Loj/PDV`, `Pneu`, `PPR`, `Adg`, `Prj`, `Bib`, `Alu`,
> `Ces` estão **praticamente vazios**: o cliente DGB usa essencialmente
> **Carteira + Faturamento + Recebimento + Estoque + Fiscal**.

## 4. Infraestrutura / utilidades (não são módulo de negócio)

| Prefixo | Função | Uso |
|---------|--------|-----|
| `SIS` | Parâmetros globais do sistema | 12 310 |
| `MIC` | **ChangeLog/ExecutionLog** do Microdata (versão/patch instalado) | 27 819 |
| `RPT` | **Gerador de relatórios/dashboards** (rpt_dashboard*, rpt_filtros, metas) | 239 053 (quase tudo `rpt_log`) |
| `LOG` | `Log_Sistema` | 95 388 |
| `USUA` | Usuários e acessos | 20 760 |
| `MAIL` | Mensagens/e-mails | 14 003 |
| `XML` | Import/export XML | 0 |
| `EDI` | Integração EDI (automotivo `SP_FAT_EDI_PACKING_LIST`) | 168 |
| `SIM` | Dicionário de FKs do framework SIM (`SIM_FK_Hint/_Columns`) | 1 016 |
| `CONN` | Conectores de integração (`DBIntegracao`) | 20 |
| `TPConflito` | Conflitos de **pacote de atualização** (não usar) | 0 |
| `MESC`, `Mescl` | Mesclagem de cadastros | 3 265 |
| `BKP`, `Temp`, `Tmp`, `TmpC` | Backup/temporárias | ~19 000 |
| `DGB` | **Customizações do cliente DGB** (grupos fiscais param, TEMP_link) | 24 835 |
| `Dola`, `Copc`, `Copd`, `Livc`, `PAF` | Tabelas de referência (dólar, COP/CFOP, PAF) | — |

## 5. Regras práticas

1. **Módulo em uso** ≈ prefixo com linhas relevantes: `CTE, REC, FAT, CAR, LIV, NOTA, FIG,
   NFE, BCO, PAG, CHEQ, CLIE, RET, CMT, CUSTO` (params), `CAR` + `CTE`.
2. **Módulo vazio** = estrutura instalada, sem operação — não portar (feature não usada).
3. **Views/procs órfãs** apontam para módulos verticais inexistentes (Estudo 14) — ignorar.
4. **Customização do cliente** vive em `DGB` (e `DBProDash`); não é padrão Microdata.
5. Prefixos de **infra** (`RPT, LOG, MIC, MAIL, TMP, BKP, TPConflito`) **não** vão para o Neon.

## 6. Relações entre módulos (macro-fluxo)

```
Cadastros (Clie/Enti/Prod/Cida) ──► Carteira (Car_Pedido)
        │                                   │
        │                                   ▼
        │                          Expedição (romaneio/coleta/separação) ──► Faturamento (Fat/Nota)
        │                                                                        │
        ├──► Compras (Cmp) ──► Recebimento/Beneficiamento (Ret) ──► Estoque (Cte/Lv3)
        │                                                                        │
        ▼                                                                        ▼
   Contas a Receber (Rec)  ◄────────────── Fiscal/SPED (Liv/Fig/Efd) ────── Contabil (não mantido)
        │
        ▼
   Financeiro/Tesouraria (Bco/CH/Cnab/FNN/Fluxo)  ◄── custo médio on-the-fly (Mcg sobre Liv)
```

## 7. Implicações para a API / Neon

1. **Escopo de porte**: núcleo = `Car`, `Fat`, `Rec`, `Pag`, `Cte`, `Liv/Fig`, `Bco`,
   `Clie/Enti`, `Ret/Cmt`. O resto é vertical vazio ou infra.
2. **Contrato de módulo → schema**: cada módulo vira um domínio em `core` (ex.: `Car` →
   `orders/shipments`; `Rec` → `receivables`; `Cte` → `inventory`).
3. **Descoberta futura**: `SELECT name FROM sys.tables` agrupado por prefixo revela módulos
   novos; tabelas de parâmetro `Prefixo_Parametros`/`_ParamEmp` marcam módulos ativos.
4. **Não portar**: `RPT`, `LOG`, `MIC`, `MAIL`, `TMP/BKP`, `TPConflito`, verticais vazios.

## 8. Números consolidados (desta base)

- 5 003 tabelas, 2 352 procs, 530 views, 672 triggers, 194 funções (Estudo 11).
- Top prefixos por volume: `CTE` 1,05 M · `REC` 590 k · `FAT` 545 k · `CAR` 452 k · `RPT` 239 k ·
  `LIV` 205 k · `LOG` 95 k · `NOTA` 72 k · `FIG` 58 k.
- Módulos de negócio realmente ativos: **~8** (Carteira, Faturamento, AR, AP, Estoque, Fiscal,
  Financeiro, Custos); o restante é esqueleto vertical ou infra.
