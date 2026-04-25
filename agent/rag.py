"""
rag.py - Sprint 4-B: RAG da base regulatoria via BM25 keyword retrieval.

Indexa arquivos .md (curados) e .pdf (textos oficiais) da pasta
`agent/regulamentos/` e devolve top-k chunks relevantes para uma query do
agente. O agente usa para ancorar citacoes regulatorias em texto verificado,
em vez de depender da memoria do LLM (que pode alucinar artigos).

Stack:
- pypdf para extracao de texto de PDFs
- rank_bm25 (Okapi BM25, puro Python) para retrieval
- Tokenizacao PT-BR simples (regex \\w+, lowercase, com normalizacao NFKD
  opcional para acentos)

Filosofia:
- Indice em memoria, construido no boot do modulo. ~1 segundo para o corpus
  curado atual (~50 chunks).
- Cache do indice via lru_cache para nao reprocessar a cada query.
- Reindex manual: chamar `reconstruir_indice()` (util quando user adiciona PDFs).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# rank_bm25 e pypdf sao deps obrigatorias. Tratados em requirements.txt.
try:
    from rank_bm25 import BM25Okapi
except ImportError as e:
    raise RuntimeError(
        "rank_bm25 nao instalado. Rode: pip install rank_bm25"
    ) from e


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PASTA_REGULAMENTOS = Path(__file__).resolve().parent / "regulamentos"

# Chunking: granularidade calibrada para corpus curado (Sprint 4-B v1).
# Chunks menores que CHUNK_TOKENS_MD favorecem BM25 mais discriminativo
# (a relevancia se concentra menos em chunks gigantes que diluem score).
CHUNK_TOKENS_MD = 200      # ~40-50 linhas de texto curado
CHUNK_TOKENS_PDF = 350     # PDFs sao mais ruidosos, chunks medianos ajudam
CHUNK_OVERLAP_TOKENS = 30  # palavras de sobreposicao entre chunks

# Stopwords PT-BR — lista mínima focada em palavras de altissima frequência.
# Reduz ruído sem precisar de dependência externa.
_STOPWORDS_PT = frozenset({
    "a", "o", "as", "os", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas",
    "para", "por", "pela", "pelo", "pelas", "pelos",
    "com", "sem", "sob", "sobre", "entre", "ate",
    "e", "ou", "mas", "que", "se", "como", "quando",
    "ser", "ter", "estar", "haver",
    "este", "esta", "isto", "esse", "essa", "isso", "aquele", "aquela", "aquilo",
    "ja", "nao", "sim", "muito", "mais", "menos", "tambem",
    "art", "artigo",  # frequentes demais em regulamentos
})


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkRegulamento:
    """Unidade indexada do corpus regulatorio."""

    fonte: str            # nome do arquivo de origem (ex: 'REN_1000_2021.md')
    chunk_id: int         # indice sequencial dentro do arquivo
    texto: str            # conteudo cru do chunk
    score: float = 0.0    # preenchido apenas em resultados de query


# ---------------------------------------------------------------------------
# Tokenizacao
# ---------------------------------------------------------------------------


_TOKEN_PAT = re.compile(r"[A-Za-z0-9À-ſ]+")


def _normalizar_acentos(texto: str) -> str:
    """Remove acentos via NFKD para matching mais robusto em PT-BR."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _tokenizar(texto: str, sem_acentos: bool = True) -> list[str]:
    """
    Tokenizador PT-BR simples para BM25:
    - lowercase
    - remove acentos (default True para tolerar typo do usuario)
    - extrai \\w+ (suporta unicode latino)
    - filtra stopwords basicas
    """
    if sem_acentos:
        texto = _normalizar_acentos(texto)
    tokens = [t.lower() for t in _TOKEN_PAT.findall(texto)]
    return [t for t in tokens if t not in _STOPWORDS_PT and len(t) >= 2]


# ---------------------------------------------------------------------------
# Loader de arquivos
# ---------------------------------------------------------------------------


def _ler_md(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _ler_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "pypdf nao instalado. Rode: pip install pypdf"
        ) from e
    reader = PdfReader(str(path))
    paginas = []
    for pagina in reader.pages:
        try:
            paginas.append(pagina.extract_text() or "")
        except Exception:
            # Pagina corrompida — pula
            continue
    return "\n\n".join(paginas)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _chunkar(
    texto: str,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """
    Divide texto em chunks de aproximadamente `chunk_tokens` palavras,
    com `overlap_tokens` de sobreposicao entre chunks consecutivos.

    Preserva limites de paragrafos quando possivel: se um paragrafo cabe
    inteiro no chunk, vai inteiro; senao, parte no proximo.
    """
    paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]

    chunks: list[str] = []
    buffer: list[str] = []
    buffer_token_count = 0

    for par in paragrafos:
        par_tokens = par.split()
        if buffer_token_count + len(par_tokens) <= chunk_tokens:
            buffer.append(par)
            buffer_token_count += len(par_tokens)
        else:
            # Fecha buffer atual
            if buffer:
                chunks.append("\n\n".join(buffer))
            # Inicia novo buffer com overlap (ultimas palavras do anterior)
            if overlap_tokens > 0 and chunks:
                ultima = chunks[-1].split()
                overlap = " ".join(ultima[-overlap_tokens:])
                buffer = [overlap, par]
                buffer_token_count = len(overlap.split()) + len(par_tokens)
            else:
                buffer = [par]
                buffer_token_count = len(par_tokens)

    if buffer:
        chunks.append("\n\n".join(buffer))

    return chunks


# ---------------------------------------------------------------------------
# Indice
# ---------------------------------------------------------------------------


@dataclass
class _IndiceBM25:
    """Indice BM25 carregado em memoria."""

    chunks: list[ChunkRegulamento]
    tokens_chunks: list[list[str]]
    bm25: BM25Okapi


_INDICE_GLOBAL: _IndiceBM25 | None = None


def _construir_indice(pasta: Path = PASTA_REGULAMENTOS) -> _IndiceBM25:
    """
    Le todos os .md e .pdf de `pasta`, particiona em chunks, tokeniza
    e constroi indice BM25 Okapi.
    """
    if not pasta.exists():
        raise FileNotFoundError(
            f"Pasta de regulamentos nao encontrada: {pasta}. "
            f"Crie a pasta e adicione arquivos .md ou .pdf."
        )

    chunks_total: list[ChunkRegulamento] = []

    arquivos = sorted(
        list(pasta.glob("*.md")) + list(pasta.glob("*.pdf"))
    )
    if not arquivos:
        raise ValueError(
            f"Nenhum arquivo .md ou .pdf em {pasta}. "
            f"Adicione regulamentos para indexar."
        )

    for arq in arquivos:
        # Pula README (nao eh corpus)
        if arq.name.lower() == "readme.md":
            continue

        if arq.suffix.lower() == ".md":
            texto = _ler_md(arq)
            chunk_tokens = CHUNK_TOKENS_MD
        else:  # .pdf
            try:
                texto = _ler_pdf(arq)
            except Exception as e:
                print(f"[rag] AVISO: falha ao ler {arq.name}: {e}")
                continue
            chunk_tokens = CHUNK_TOKENS_PDF

        if not texto.strip():
            continue

        chunks_arq = _chunkar(
            texto,
            chunk_tokens=chunk_tokens,
            overlap_tokens=CHUNK_OVERLAP_TOKENS,
        )

        for idx, ck in enumerate(chunks_arq):
            chunks_total.append(
                ChunkRegulamento(
                    fonte=arq.name,
                    chunk_id=idx,
                    texto=ck,
                )
            )

    if not chunks_total:
        raise ValueError(f"Nenhum chunk extraido dos arquivos em {pasta}.")

    tokens_chunks = [_tokenizar(c.texto) for c in chunks_total]
    bm25 = BM25Okapi(tokens_chunks)

    print(
        f"[rag] Indice construido: {len(chunks_total)} chunks de "
        f"{len(arquivos)} arquivo(s)."
    )

    return _IndiceBM25(
        chunks=chunks_total,
        tokens_chunks=tokens_chunks,
        bm25=bm25,
    )


def reconstruir_indice() -> int:
    """
    Forca reconstrucao do indice (util quando o usuario adicionou novos
    arquivos sem reiniciar o servidor). Retorna o numero de chunks.
    """
    global _INDICE_GLOBAL
    _INDICE_GLOBAL = _construir_indice()
    return len(_INDICE_GLOBAL.chunks)


def _obter_indice() -> _IndiceBM25:
    """Singleton do indice. Constroi na primeira chamada."""
    global _INDICE_GLOBAL
    if _INDICE_GLOBAL is None:
        _INDICE_GLOBAL = _construir_indice()
    return _INDICE_GLOBAL


# ---------------------------------------------------------------------------
# Funcao publica de retrieval
# ---------------------------------------------------------------------------


def consultar_regulamento(
    query: str,
    top_k: int = 3,
    score_minimo: float = 0.5,
) -> list[ChunkRegulamento]:
    """
    Retorna os top-k chunks mais relevantes para a query.

    Parameters
    ----------
    query : str
        Pergunta ou termo de busca em PT-BR.
    top_k : int, default 3
        Numero maximo de resultados.
    score_minimo : float, default 1.0
        Filtro de relevancia. BM25 scores tipicos: 0-30 para corpus pequeno.
        Use 0.0 para devolver tudo (debug).

    Returns
    -------
    list of ChunkRegulamento
        Ordenados por score decrescente. Pode retornar lista vazia se
        nenhum chunk passar do score_minimo.
    """
    if not query.strip():
        return []

    indice = _obter_indice()
    query_tokens = _tokenizar(query)
    if not query_tokens:
        return []

    scores = indice.bm25.get_scores(query_tokens)

    # Indices ordenados por score desc
    pares = sorted(enumerate(scores), key=lambda p: p[1], reverse=True)

    resultados: list[ChunkRegulamento] = []
    for idx, score in pares[:top_k]:
        if score < score_minimo:
            break
        chunk = indice.chunks[idx]
        # Cria copia com score preenchido (dataclass eh frozen)
        resultados.append(
            ChunkRegulamento(
                fonte=chunk.fonte,
                chunk_id=chunk.chunk_id,
                texto=chunk.texto,
                score=float(score),
            )
        )

    return resultados


# ---------------------------------------------------------------------------
# CLI: rebuild manual
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rebuild":
        n = reconstruir_indice()
        print(f"OK. {n} chunks indexados.")
        sys.exit(0)

    # Demo: roda algumas queries e mostra top-3
    queries_demo = [
        "qual a multa de ultrapassagem de demanda?",
        "Lei 14.300 transicao TUSD",
        "hospital UTI autonomia minima",
        "tarifa Enel SP A4 Verde ponta fora-ponta",
        "como funciona compensacao de geracao distribuida?",
    ]

    print("=== Demo do RAG ===")
    for q in queries_demo:
        print(f"\nQuery: {q!r}")
        resultados = consultar_regulamento(q, top_k=2)
        for r in resultados:
            preview = r.texto.replace("\n", " ")[:200]
            print(f"  [{r.score:.2f}] {r.fonte} (chunk {r.chunk_id})")
            print(f"    {preview}...")
