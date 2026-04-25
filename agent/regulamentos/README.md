# Base regulatória do BESS Sizing Copilot

Pasta indexada pelo RAG (`agent/rag.py`) para consulta via tool
`consultar_base_regulatoria`. Sempre que o agente precisar citar artigo
específico de regulamento, ele consulta este corpus em vez de depender
do conhecimento interno do LLM (que pode alucinar números de artigos).

## Conteúdo atual (Sprint 4-B v1)

Arquivos `.md` com **resumos curados** dos pontos relevantes para
dimensionamento de BESS. Não substituem leitura dos textos oficiais —
servem como base de retrieval para o agente justificar decisões com
ancoragem regulatória.

| Arquivo | Origem | Status |
|---------|--------|--------|
| `REN_1000_2021.md` | Resolução Normativa ANEEL nº 1.000/2021 | Curado (artigos-chave) |
| `LEI_14300_2022.md` | Lei nº 14.300/2022 — Marco Legal da GD | Curado |
| `NBR_13534.md` | ABNT NBR 13534 — Instalações elétricas em estabelecimentos de saúde | Curado |
| `REH_3477_2025_ENEL_SP_A4_VERDE.md` | Resolução Homologatória ANEEL nº 3.477/2025 | Verificado (caso real) |

## Como adicionar novo regulamento

### Opção 1 — Markdown curado (recomendado para artigos-chave)

Crie um arquivo `NOME_DO_REGULAMENTO.md` com:

```markdown
# Título oficial

**Fonte:** URL oficial
**Vigência:** data
**Aplicação:** classes/setores afetados

## Artigo X — Tema

Texto do artigo OU resumo verificado.

## Artigo Y — Tema

...
```

Reindexação acontece automaticamente no próximo boot do agente OU rode
`python agent/rag.py rebuild` manualmente.

### Opção 2 — PDF completo

Coloque o PDF nesta pasta. O indexador extrai texto via `pypdf` e
particiona em chunks de ~500 tokens com overlap. Funciona bem para
documentos densos (NBRs, resoluções longas).

Trade-off: PDFs grandes geram muitos chunks e BM25 pode retornar
seções tangenciais. Markdown curado tem precisão maior.

## Limitações conhecidas

- **NBR 13534** está atrás de paywall ABNT. O `.md` curado contém apenas
  os pontos públicos sobre Grupo 1 (UTI/centro cirúrgico) que aparecem
  em material técnico secundário (manuais Eletrobras PROCEL, periódicos
  acadêmicos).
- **Atualizações tarifárias** (REHs) precisam ser adicionadas
  manualmente quando ANEEL publicar novos valores.
- **BM25 keyword-only** — não captura sinônimos automaticamente
  ("multa de demanda" vs "penalidade de ultrapassagem"). Para semântica
  mais robusta, considere upgrade para embeddings (Sprint 4-B v2).
