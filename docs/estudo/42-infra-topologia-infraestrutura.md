# Estudo 42 — Infraestrutura (topologia, parametrização, SIMConnect, replicação, agendadores)

> **Data:** 19/set/2026
> **Escopo:** Topologia multi-tenant do servidor (42 bases), parametrização central (`Empresas`, `Sistemas_Config`, `*ParamEmp`), RLS (`microdata.Empresas`), serviço SIMConnect (`Conn_*`, `mic_*`, `DBIntegracao`), replicação/integração entre bases, agendadores de relatório e logs de infra.
> **Restrições:** apenas leitura; sem objetos novos em produção.
> **Relações:** Estudos 03–41 (todos os módulos); define o acesso multi-empresa para a API nova (contrato `microdata`).

---

## 1. Topologia do servidor (multi-tenant)

O servidor SQL (`10.156.0.124`) hospeda **42 bases visíveis** (29 + sistema), agrupadas por função:

| Prefixo | Qtd | Papel |
|---------|-----|-------|
| `DBMicrodata_*` | 16 (+2 `_Log`) | **ERP por cliente** (AndradeGomes, BigFashion, Demo, **DGB**, EZDecor, Flora, Helvetia, MarioTanno, Orthocrem, RSMartinelli, Technische, Tecitex, Tellaio, Teste, Tordera, TresEllos + `EZDecor_Log`/`Tellaio_Log`) |
| `DBCon_*` | 19 | Base de **conexão/integração do cliente** (DGB, EZDecor, Paige, Renato, Zerada… — contém `Trn_*`, `Cont_*`, `CTE_*`, `Sistemas_Config`) |
| `DBInternet_*` | 3 | Portal internet (EZDecor, Tellaio_01, Tellaio_04) — **DGB não possui** |
| `DBIntegracao` | 1 | Central do **SIMConnect** (licenças/endpoints/IBPT) |
| `DBProDash` | 1 | Camada BI atual (tabelas avulsas de estudo) |

- `DBMicrodata_DGB` = **5.004 tabelas** `dbo` (schema `microdata` = 1 view); é o ERP em produção estudado.
- `DBProDash` (BI atual): `dgbcomexEstoque(-Retroativo)`, `estoqueDGB(-Analitico)`, `estoqueDIFF`, `estoqueEQUAL`, `estoqueMOVEN`, `Rel_CCusto_Niveis`, `tab_dup`, `nova_tabela` — **estudo avulso** (não é DW); reforça a decisão de migrar BI para Neon.
- `DBCon_DGB` (90 tabelas): `Cont_*` (contábil), `CTE_*`, `Fab_*`, `Fat_*`, `Fin_*`, `Pag_*`, `Rec_*`, `Sistemas_Config(_Itens)`, `Trn_NotaFiscal`/`Trn_Pessoa`/`Trn_Serie` (tabelas de transferência), `Vendas_DBF`.

---

## 2. Empresas (`dbo.Empresas`) e RLS

5 empresas cadastradas no ERP DGB:

| Cod | Razão social | UF | CNPJ | Id |
|-----|--------------|----|------|----|
| `01` | PRO MODA TEXTIL LTDA (fabricante) | SP | 07.695.188/0001-89 | 1 |
| `02` | MICRODATA DEMONSTRACAO | SP | 00.000.000/0000-00 | 2 |
| `03` | NOTA DE DEBITO | SP | — | 3 |
| `13` | **DGB COMERCIO IMPORTACAO E EXPORTACAO LTDA** | SC | 27.616.615/0001-01 | 4 |
| `14` | DEMONSTRACAO | SP | — | 5 |

Dados úteis da `Empresas` (DGB, Id 4): CNAE `4641901` (comércio varejista têxtil), Regime Trib `3` (lucro real), Inscr. Est. `258313420`, endereço BR-101 KM 131 Camboriú/SC.

**Restrição de linha (RLS)** — view `microdata.Empresas`:

```sql
select F.* from dbo.Empresas F
where exists (select 0 from SIS_UsuarioEmpresa UE
              inner join Usuarios U on U.Cod_Usuario = UE.Cod_Usuario
              where UE.ID_Empresa = F.Id_Empresa and Upper(U.Nome_Usuario) = Upper(SUSER_NAME()))
   or not exists (select 0 from SIS_UsuarioEmpresa UE
              inner join Usuarios U on U.Cod_Usuario = UE.Cod_Usuario
              where Upper(U.Nome_Usuario) = Upper(SUSER_NAME()))
```

→ Se o login SQL **não** tem vínculo usuário×empresa, **vê todas** as empresas. O login read-only `sadgb` não tem vínculo → visão completa (comportamento desejado para a API/BI).

---

## 3. Parametrização central

| Tabela | Onde | Conteúdo |
|--------|------|----------|
| `Etc_Parametros` | `DBInternet_*` (portal) | Params do portal internet — **DGB não tem** (referências em procs como `SP_CMT_Calcula_SaldoEmAberto` → `DBInternet_DGB.dbo.Etc_Parametros` são ignoradas); EZDecor/Tellaio possuem |
| `Sistemas_Config` / `_Itens` | ERP e `DBCon_*` | Configuras por sistema (`Conf_Chave`, `Conf_Exibir`; itens com `ConfI_StoredProc/Tabela/Campo/Tipo/Condicao`) — telas de parâmetros dinâmicas |
| `*_Parametros` / `*_ParamEmp` | por módulo | Ex.: `Ret_ParamEmp`, `Cmt_Parametros`+`Cmt_ParamEmp`, `Pag_Parametros`, `Cont_Param_Plano_Contas`, `Fab_ParamEmp`, `mnu_Parametros` (mapeados nos estudos de cada módulo) |
| `Empresas` | ERP | cadastro de empresas (acima) + `Usuario_EmpresaPadrao`/`SIS_UsuarioEmpresa` |
| `SIS_EmpresaPadrao_Usuario` / `usuario_empresa` | ERP | empresa principal por usuário |

Regras comuns observadas nos `*_Parametros`: integração com outros sistemas (`Integra_Pagar/SIMRec/Contabil`), empresa única ativa (`Usar_Todas`/`Empresa`), QMP/unidades, aprovações. Padrão a replicar na config da API nova.

---

## 4. SIMConnect (`Conn_*`, `mic_*`, `DBIntegracao`)

**Serviço de conexão/licença da Microdata** — sincroniza licenças, exceções, IBPT e endpoints com a nuvem da Microdata via REST.

### 4.1 Local (no ERP)

| Tabela | Linhas | Conteúdo |
|--------|--------|----------|
| `Conn_Logs` | 3 | Atualizações de **licença** do EXE (cliente `27.616.615/0001-01`, processo `Licença`, tipo `Atualização`, status `C`/`E`; ex.: falha REST timeout) |
| `Conn_Timers` | 3 | Última sincronização por recurso: `Endpoints`, `Logs`, `LogExceptions` (diária, última em set/2026) |
| `Conn_LogExceptions` | — | Exceções do cliente (empresa, usuário, sistema, versão, tela, `msg_erro`, `tipo_licenca`, `enviada`) |
| `Mic_Filtro` / `Mic_Filtro_Conf` | — | Filtros salvos por usuário/tela (Tabela/Campo/Operador/Filtro/Valores) |
| `mic_ChangeLog_Event` / `mic_ExecutionLog_Event` | — | Log de eventos de DDL (SQL Server) do SIMConnect (objeto, versão, patch, XML da definição) |

### 4.2 Central (`DBIntegracao`)

`Conn_Clientes`, `Conn_Clientes_Licenca`, `Conn_Clientes_Sistemas`, `Conn_Endpoints`, `Conn_LogExceptions` (ponto de coleta), `Conn_Logs`, `Conn_Parametros`, `Conn_Sistemas`, **`Conn_TabelaIBPT`** (tabela IBPT de impostos federal).

---

## 5. Replicação e integração entre bases

- **Replicação de ficha técnica (fábrica)**: `CTE_Ficha_Tecnica_Replicacao` + `SP_CTE_ReplicacaoFTJob` (job que replica FT entre bases `DBMicrodata_*`/`DBCon_*`).
- **Replicação de exclusividade/custos**: `SP_Car_ReplicarExclusividade`, `SP_Custo_Replicar`, `SP_TNT_Replicar_Obs`, `sp_fioReplicarDigitacaoProcesso`.
- **Integração loja (SIMLoja/SIMRet)**: `Ret_EnviaPedidoCompra`, `Ret_EnviaStatusPedCompra`, `Ret_maior_lancto` (envio de pedidos compra/status entre loja e matriz).
- **Transferência de dados**: `DBCon_*` → tabelas `Trn_*` (NotaFiscal, Pessoa, Serie); `DBInternet_*` para portal.

---

## 6. Agendadores

| Tabela | Módulo | Conteúdo |
|--------|--------|----------|
| `Rep_Agendamentos` | SIMReport | Agendamentos de relatórios (Hora, Tipo) |
| `Loj_Agendamentos` | SIMLoja | Agendamentos de loja |
| `Tnt_IntAgendamentos` | SIMTinturaria | Agendamentos de tinturaria |
| `agenda` | SIMAgenda | Agenda/calendário (id_perfil, título, data_início/fim, descrição, codigo_cliente, cor) |
| `Conn_Timers` | SIMConnect | Timer de sincronização de recursos |
| SQL Agent (`msdb`) | — | Jobs de replicação (ex. `SP_CTE_ReplicacaoFTJob`) |

---

## 7. Observações para a nova API

1. **Fonte única**: API lerá somente `DBMicrodata_DGB` (via login read-only sem RLS) e gravará **Neon** (PostgreSQL, schemas `raw`/`core`/`marts`/`etl`). `DBProDash` é avulso e descartável (substituir por marts no Neon).
2. **Multiempresa**: o "código" de empresa é `Empresas.Codigo_Empresas` (char `'13'`, padding); `Id_Empresa` é o int (1..5). O contrato de API deve usar **Codigo_Empresas** por compatibilidade com as tabelas (`Empresa` char(2) em todo o ERP).
3. **Config**: replicar o modelo de `*_Parametros`/`Sistemas_Config` para config da API (chave-valor reativa no ETL); não depender de `DBInternet_*`/`Etc_Parametros` (DGB não tem).
4. **Replicação**: a API é read-only e não participa da replicação do ERP; o ETL para Neon deve ser **incremental por marca-d'água** (`Ult_Atualizacao`, `Data_Hora`, identidades) — padrões já levantados nos estudos 03–41.
5. **Logs de infra** (`Conn_*`, `mic_*`) não entram no contrato; para observabilidade da API usar tooling próprio (logs estruturados no Neon/CloudWatch).
6. **RLS**: se a API futura expuser dados por usuário, reaproveitar o conceito `SIS_UsuarioEmpresa`↔`Empresas.Id_Empresa` e materializar a visão por token; evitar filtrar por `SUSER_NAME()` (a API terá seu próprio login de serviço).
7. **Licenciamento/IBPT**: `DBIntegracao.Conn_TabelaIBPT` é a fonte de impostos federais IBPT (usada em NFe quando não configurada) — confirmar necessidade para a mart fiscal.

---

## 8. Status da fila de módulos

Com o Estudo 42 (Infra) encerra o **mapa de módulos** previsto. Estudos concluídos: 03–42 (Prefixo/Arquitetura, Estoque, Produtos, Fabricação, Tinturaria, Faturamento/NF, Vendas, Custos, Financeiro, Faturamento detalhado, PCP, CRM, Ponto de venda, Folha, Projetos, Pedidos, Impressão, Agendador, Relatórios, Retaguarda, Cartetas, Lojas, Beneficiamento, Bonificação, Mala real, Automação, Convenenção, Importação de arquivos (Bom Retiro), Compras (SIMCompras), Fiscal, CMV/Inventário, SPED, Custo/CMV+Produtivo, Custos MCG, RET/SIMRET, COMEX, Compras `Cmt_*`, RPT, Usua, Infra) + 2 docs do legado oraculum + este índice.

---

_Fontes: pesquisa em `sys.databases`, `sys.tables` (cross-DB), `INFORMATION_SCHEMA.COLUMNS`, defs de procs (`SP_CMT_Calcula_SaldoEmAberto`, `Ret_EnviaPedidoCompra`, `SP_CTE_ReplicacaoFTJob`), definição de `microdata.Empresas` e amostragem de `Empresas`, `Conn_*`, `DBIntegracao`/`DBProDash`/`DBCon_DGB`._