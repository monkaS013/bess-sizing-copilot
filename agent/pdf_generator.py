"""
pdf_generator.py - Gerador de PDF da proposta executiva (Sprint 4 Fase A).

Recebe a lista de mensagens de uma sessao, identifica a ultima resposta do
agente (a proposta executiva final), parseia o markdown e renderiza um PDF
profissional com header HDT Energy + BESS Sizing Copilot, footer paginado
e estilo corporativo (azul-marinho + laranja accent).

Dependencias: reportlab>=4.0, markdown-it-py>=3.0.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from markdown_it import MarkdownIt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------------------------
# Identidade visual
# ---------------------------------------------------------------------------

# Paleta corporativa HDT Energy + BESS Sizing Copilot
COR_PRIMARIA = colors.HexColor("#0B2545")    # azul-marinho
COR_ACCENT = colors.HexColor("#E76F00")      # laranja energia
COR_CINZA_FORTE = colors.HexColor("#3A3A3A")
COR_CINZA_CLARO = colors.HexColor("#F2F4F7")
COR_LINHA = colors.HexColor("#D0D5DD")

PRODUTO = "BESS Sizing Copilot"
EMPRESA = "HDT Energy"
SUBTITULO = "Proposta Tecnico-Comercial BESS"


# ---------------------------------------------------------------------------
# Estilos de paragrafo
# ---------------------------------------------------------------------------


def _construir_estilos() -> dict[str, ParagraphStyle]:
    """Cria estilos de paragrafo customizados para a proposta."""
    base = getSampleStyleSheet()
    estilos: dict[str, ParagraphStyle] = {}

    estilos["TituloPrincipal"] = ParagraphStyle(
        "TituloPrincipal",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=COR_PRIMARIA,
        spaceBefore=0,
        spaceAfter=4,
    )
    estilos["Subtitulo"] = ParagraphStyle(
        "Subtitulo",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=12,
        textColor=COR_CINZA_FORTE,
        spaceAfter=14,
    )
    estilos["Heading1"] = ParagraphStyle(
        "BessHeading1",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=COR_PRIMARIA,
        spaceBefore=14,
        spaceAfter=6,
    )
    estilos["Heading2"] = ParagraphStyle(
        "BessHeading2",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=COR_PRIMARIA,
        spaceBefore=10,
        spaceAfter=4,
    )
    estilos["Heading3"] = ParagraphStyle(
        "BessHeading3",
        parent=base["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=COR_CINZA_FORTE,
        spaceBefore=8,
        spaceAfter=3,
    )
    estilos["Body"] = ParagraphStyle(
        "BessBody",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=COR_CINZA_FORTE,
        spaceBefore=2,
        spaceAfter=6,
        alignment=4,  # justify
    )
    estilos["BulletItem"] = ParagraphStyle(
        "BessBullet",
        parent=estilos["Body"],
        leftIndent=14,
        bulletIndent=2,
        spaceBefore=0,
        spaceAfter=2,
    )
    estilos["Pequeno"] = ParagraphStyle(
        "BessPequeno",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=COR_CINZA_FORTE,
    )
    return estilos


# ---------------------------------------------------------------------------
# Header / Footer
# ---------------------------------------------------------------------------


def _desenhar_header_footer(canvas, doc) -> None:
    """Header com EMPRESA + PRODUTO. Footer com paginacao + timestamp."""
    canvas.saveState()
    largura, altura = A4

    # Faixa superior colorida fina
    canvas.setFillColor(COR_PRIMARIA)
    canvas.rect(0, altura - 8 * mm, largura, 8 * mm, fill=1, stroke=0)

    # Header texto
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(15 * mm, altura - 5.5 * mm, EMPRESA.upper())

    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(largura - 15 * mm, altura - 5.5 * mm, PRODUTO)

    # Footer linha
    canvas.setStrokeColor(COR_LINHA)
    canvas.setLineWidth(0.5)
    canvas.line(15 * mm, 15 * mm, largura - 15 * mm, 15 * mm)

    # Footer texto esquerda
    canvas.setFillColor(COR_CINZA_FORTE)
    canvas.setFont("Helvetica", 8)
    rodape_esq = doc.rodape_esq if hasattr(doc, "rodape_esq") else ""
    canvas.drawString(15 * mm, 10 * mm, rodape_esq)

    # Footer texto direita: pagina X
    canvas.drawRightString(
        largura - 15 * mm,
        10 * mm,
        f"Pag. {doc.page}",
    )

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Markdown -> Platypus (parser limitado, focado no que o agente produz)
# ---------------------------------------------------------------------------


_INLINE_BOLD_PAT = re.compile(r"\*\*(.+?)\*\*")
_INLINE_ITALIC_PAT = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_INLINE_CODE_PAT = re.compile(r"`([^`]+)`")
_INLINE_LINK_PAT = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _escape_xml(text: str) -> str:
    """Escape para Paragraph (que usa mini-XML do reportlab)."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _render_inline(text: str) -> str:
    """Converte sintaxe inline markdown em tags Paragraph do reportlab."""
    text = _escape_xml(text)
    # Codigo inline antes do bold (para nao quebrar nested)
    text = _INLINE_CODE_PAT.sub(
        lambda m: f'<font face="Courier" size="9">{m.group(1)}</font>',
        text,
    )
    text = _INLINE_BOLD_PAT.sub(r"<b>\1</b>", text)
    text = _INLINE_ITALIC_PAT.sub(r"<i>\1</i>", text)
    text = _INLINE_LINK_PAT.sub(
        r'<link href="\2" color="#0B6BCB"><u>\1</u></link>',
        text,
    )
    return text


def _markdown_para_platypus(
    md_texto: str,
    estilos: dict[str, ParagraphStyle],
) -> list[Any]:
    """
    Parser markdown -> lista de Flowables (reportlab Platypus).

    Suporta: H1-H3, paragrafos, bold/italic/code inline, listas
    (bulleted/numbered), tabelas (GFM). Ignora HTML inline e blocos de codigo
    (renderiza como Preformatted).
    """
    md = MarkdownIt("commonmark", {"breaks": False, "html": False}).enable("table")
    tokens = md.parse(md_texto)

    flowables: list[Any] = []
    i = 0
    n = len(tokens)

    while i < n:
        tk = tokens[i]
        kind = tk.type

        # ----- Headings -----
        if kind == "heading_open":
            tag = tk.tag  # h1, h2, h3...
            inline = tokens[i + 1]
            texto = _render_inline(inline.content)
            estilo_key = {"h1": "Heading1", "h2": "Heading2", "h3": "Heading3"}.get(
                tag, "Heading3"
            )
            flowables.append(Paragraph(texto, estilos[estilo_key]))
            # Avanca: heading_open + inline + heading_close
            i += 3
            continue

        # ----- Paragrafo simples -----
        if kind == "paragraph_open":
            inline = tokens[i + 1]
            texto = _render_inline(inline.content)
            if texto.strip():
                flowables.append(Paragraph(texto, estilos["Body"]))
            i += 3
            continue

        # ----- Lista nao-ordenada -----
        if kind == "bullet_list_open":
            j, items = _coletar_lista(tokens, i, fim_token="bullet_list_close")
            for item_texto in items:
                flowables.append(
                    Paragraph(
                        f'&bull; {_render_inline(item_texto)}',
                        estilos["BulletItem"],
                    )
                )
            i = j + 1
            continue

        # ----- Lista ordenada -----
        if kind == "ordered_list_open":
            j, items = _coletar_lista(tokens, i, fim_token="ordered_list_close")
            for idx, item_texto in enumerate(items, start=1):
                flowables.append(
                    Paragraph(
                        f'{idx}. {_render_inline(item_texto)}',
                        estilos["BulletItem"],
                    )
                )
            i = j + 1
            continue

        # ----- Tabela -----
        if kind == "table_open":
            j, tabela = _coletar_tabela(tokens, i)
            if tabela:
                flowables.append(_montar_tabela_pdf(tabela))
                flowables.append(Spacer(1, 4))
            i = j + 1
            continue

        # ----- Linha horizontal -----
        if kind == "hr":
            flowables.append(Spacer(1, 4))
            t = Table([[""]], colWidths=[16 * cm], rowHeights=[0.5])
            t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, COR_LINHA)]))
            flowables.append(t)
            flowables.append(Spacer(1, 6))
            i += 1
            continue

        # ----- Fence (bloco de codigo) — render plain -----
        if kind == "fence":
            texto = _escape_xml(tk.content)
            flowables.append(
                Paragraph(
                    f'<font face="Courier" size="8">{texto}</font>',
                    estilos["Body"],
                )
            )
            i += 1
            continue

        # Fallback: pula token desconhecido (HTML, soft_break solto, etc.)
        i += 1

    return flowables


def _coletar_lista(
    tokens: list, inicio: int, fim_token: str
) -> tuple[int, list[str]]:
    """
    Percorre uma lista markdown e retorna (indice_do_close, [textos_dos_itens]).

    Cada item agrega o texto inline do paragrafo dentro dele.
    """
    items: list[str] = []
    n = len(tokens)
    i = inicio + 1
    item_atual: list[str] = []
    dentro_item = False

    while i < n:
        tk = tokens[i]
        if tk.type == fim_token:
            return i, items
        if tk.type == "list_item_open":
            dentro_item = True
            item_atual = []
        elif tk.type == "list_item_close":
            items.append(" ".join(item_atual).strip())
            dentro_item = False
        elif dentro_item and tk.type == "inline":
            item_atual.append(tk.content)
        i += 1

    # Caso nao encontre o close (markdown malformado), devolve o que tem
    return n - 1, items


def _coletar_tabela(tokens: list, inicio: int) -> tuple[int, list[list[str]]]:
    """
    Percorre uma tabela GFM e retorna (indice_do_table_close, linhas[col1,col2,...]).
    """
    linhas: list[list[str]] = []
    linha_atual: list[str] = []
    n = len(tokens)
    i = inicio + 1
    dentro_celula = False

    while i < n:
        tk = tokens[i]
        if tk.type == "table_close":
            return i, linhas
        if tk.type == "tr_open":
            linha_atual = []
        elif tk.type == "tr_close":
            if linha_atual:
                linhas.append(linha_atual)
        elif tk.type in ("th_open", "td_open"):
            dentro_celula = True
        elif tk.type in ("th_close", "td_close"):
            dentro_celula = False
        elif dentro_celula and tk.type == "inline":
            linha_atual.append(tk.content)
        i += 1

    return n - 1, linhas


def _montar_tabela_pdf(linhas: list[list[str]]) -> Table:
    """Constroi um Platypus Table com estilo corporativo."""
    if not linhas:
        return Table([[""]])

    # Renderiza inline em cada celula (vira Paragraph para suportar wrap)
    estilo_celula = ParagraphStyle(
        "celula",
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        textColor=COR_CINZA_FORTE,
    )
    estilo_header = ParagraphStyle(
        "celula_header",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.white,
    )

    body_data: list[list[Any]] = []
    for idx, row in enumerate(linhas):
        rendered = []
        for c in row:
            txt = _render_inline(c)
            estilo = estilo_header if idx == 0 else estilo_celula
            rendered.append(Paragraph(txt, estilo))
        body_data.append(rendered)

    # Determina larguras: divide igualmente o espaco util
    largura_util = 17 * cm
    n_cols = max(1, len(linhas[0]))
    col_widths = [largura_util / n_cols] * n_cols

    tabela = Table(body_data, colWidths=col_widths, repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COR_PRIMARIA),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, COR_PRIMARIA),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COR_CINZA_CLARO]),
                ("LINEBELOW", (0, "splitlast"), (-1, "splitlast"), 0.3, COR_LINHA),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tabela


# ---------------------------------------------------------------------------
# Extracao de dados da sessao
# ---------------------------------------------------------------------------


def _msg_field(m: Any, key: str, default: Any = None) -> Any:
    """
    Le um campo de uma MensagemRegistro (dataclass) OU de um dict.

    Centraliza a extracao porque a sessao pode vir do storage (dataclass)
    ou de um payload JSON (dict, em testes).
    """
    if isinstance(m, dict):
        return m.get(key, default)
    return getattr(m, key, default)


def _extrair_proposta_final(mensagens: Iterable[Any]) -> str | None:
    """
    Procura a ULTIMA mensagem do assistant que pareca ser uma proposta
    executiva final. Heuristica: ultima msg do assistant com >= 400
    caracteres E que tenha headings/tabelas (markdown estruturado).

    Se nao achar nada estruturado, retorna a ultima resposta do assistant
    independente do tamanho.
    """
    candidatas: list[str] = []
    for m in mensagens:
        role = _msg_field(m, "role")
        content = _msg_field(m, "content", "")
        erro = _msg_field(m, "erro")
        if role == "assistant" and content and not erro:
            candidatas.append(content)

    if not candidatas:
        return None

    # Da preferencia a ultima resposta substancial e estruturada
    for content in reversed(candidatas):
        tem_heading = bool(re.search(r"^#{1,3}\s+", content, re.MULTILINE))
        tem_tabela = "|" in content and "---" in content
        if len(content) >= 400 and (tem_heading or tem_tabela):
            return content

    # Fallback: ultima resposta independente do tamanho
    return candidatas[-1]


def _extrair_titulo_caso(mensagens: Iterable[Any]) -> str:
    """
    Tenta extrair um titulo do caso a partir da PRIMEIRA mensagem do user.

    Heuristica: pega ate o primeiro ponto final ou 80 caracteres.
    """
    for m in mensagens:
        role = _msg_field(m, "role")
        content = _msg_field(m, "content", "")
        if role == "user" and content:
            # Limpa newlines e pega o primeiro pedaco substancial
            primeira_linha = content.replace("\n", " ").strip()
            # Procura por primeira frase (ate primeiro ponto final)
            match = re.match(r"^(.+?\.)\s", primeira_linha)
            if match:
                titulo = match.group(1)
            else:
                titulo = primeira_linha[:120]
            if len(titulo) > 120:
                titulo = titulo[:117] + "..."
            return titulo
    return "Proposta tecnico-comercial"


# ---------------------------------------------------------------------------
# Construcao do documento
# ---------------------------------------------------------------------------


def _agora_brasil() -> str:
    """Timestamp legivel em PT-BR (UTC-3 aproximado)."""
    agora = datetime.now(timezone.utc)
    return agora.strftime("%d/%m/%Y %H:%M UTC")


def gerar_proposta_pdf(
    mensagens: list[Any],
    session_id: str,
    modelo: str | None = None,
) -> bytes:
    """
    Gera PDF da proposta executiva.

    Parameters
    ----------
    mensagens : list of MensagemRegistro or dict
        Lista de mensagens da sessao (em ordem cronologica).
    session_id : str
        ID da sessao (vai pro footer).
    modelo : str, optional
        Nome do modelo Claude usado (vai pra secao de metadata).

    Returns
    -------
    bytes
        Conteudo do PDF.

    Raises
    ------
    ValueError
        Se nao houver proposta final identificavel na sessao.
    """
    proposta_md = _extrair_proposta_final(mensagens)
    if not proposta_md:
        raise ValueError(
            "Nao ha resposta do agente nesta sessao para exportar como proposta."
        )

    titulo_caso = _extrair_titulo_caso(mensagens)
    estilos = _construir_estilos()
    timestamp = _agora_brasil()

    buffer = io.BytesIO()

    # Margens A4: 15mm em cada lado
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{SUBTITULO} - {titulo_caso[:60]}",
        author=EMPRESA,
        subject=PRODUTO,
        creator=f"{PRODUTO} (BESS Sizing Copilot)",
    )

    # Frame ocupa toda a area util entre header e footer
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height - 2 * mm,  # margem extra abaixo do header
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        showBoundary=0,
    )

    # Footer customizado
    doc.rodape_esq = (
        f"Sessao {session_id[:8]}... gerado em {timestamp}"
        + (f" - modelo {modelo}" if modelo else "")
    )

    template = PageTemplate(
        id="default",
        frames=[frame],
        onPage=_desenhar_header_footer,
    )
    doc.addPageTemplates([template])

    # ---------- Conteudo ----------
    story: list[Any] = []

    # Titulo principal
    story.append(Paragraph(SUBTITULO, estilos["TituloPrincipal"]))
    story.append(
        Paragraph(
            f"<b>Caso analisado:</b> {_escape_xml(titulo_caso)}",
            estilos["Subtitulo"],
        )
    )

    # Linha divisoria laranja
    linha = Table([[""]], colWidths=[17 * cm], rowHeights=[2])
    linha.setStyle(
        TableStyle(
            [("BACKGROUND", (0, 0), (-1, -1), COR_ACCENT)]
        )
    )
    story.append(linha)
    story.append(Spacer(1, 10))

    # Corpo: render do markdown da proposta
    story.extend(_markdown_para_platypus(proposta_md, estilos))

    # Pagina final com metadata + disclaimer
    story.append(PageBreak())
    story.append(Paragraph("Sobre esta proposta", estilos["Heading1"]))
    story.append(
        Paragraph(
            (
                f"Documento gerado automaticamente pelo <b>{PRODUTO}</b>, "
                f"sistema de dimensionamento de Sistemas de Armazenamento de "
                f"Energia (BESS) desenvolvido pela {EMPRESA}. Os calculos "
                f"obedecem a REN ANEEL 1.000/2021, Lei 14.300/2022 e ABNT "
                f"NBR 16690/5410, com modelo de degradacao via equacao de "
                f"Arrhenius calibrado contra fichas tecnicas Tier 1 (Huawei "
                f"LUNA2000, CATL EnerOne)."
            ),
            estilos["Body"],
        )
    )

    story.append(Paragraph("Premissas e ressalvas gerais", estilos["Heading2"]))
    bullets_premissas = [
        "Tarifas referenciadas via Resolucoes Homologatorias ANEEL vigentes na data da consulta.",
        "Perfil de carga sintetico baseado nos dados informados pelo cliente; recomenda-se medicao real (15min, 12 meses) para engenharia de detalhe.",
        "CAPEX referencia 2024-2025 instalado; cotacao formal recomendada antes de tomada de decisao final.",
        "Modelo de degradacao linear ate 80% de SoH, sem modelagem de knee point.",
        "Analise de sensibilidade tornado +-20% nas variaveis CAPEX, OPEX, economia e WACC.",
        "Esta proposta nao substitui projeto eletrico, laudo tecnico ou ART de profissional habilitado.",
    ]
    for b in bullets_premissas:
        story.append(Paragraph(f"&bull; {_escape_xml(b)}", estilos["BulletItem"]))

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            f"<i>Documento gerado em {timestamp} - sessao {session_id}</i>",
            estilos["Pequeno"],
        )
    )

    doc.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Smoke test (rodar diretamente: python pdf_generator.py)
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    from pathlib import Path

    msgs = [
        {
            "role": "user",
            "content": (
                "Quero dimensionar um BESS para uma industria metalurgica de medio "
                "porte na regiao metropolitana de Campinas/SP, atendida pela Enel "
                "SP, classe A4 modalidade verde."
            ),
            "erro": None,
        },
        {
            "role": "assistant",
            "content": """# Proposta Executiva — BESS Peak Shaving

## 1. Diagnostico

A metalurgica registra pico de **800 kW** por 2 horas diarias em dias uteis,
contra demanda contratada de 600 kW, gerando 200 kW de ultrapassagem mensal.

## 2. Sizing Recomendado

| Parametro | Valor |
|-----------|-------|
| Energia nominal | 509,7 kWh |
| Potencia nominal | 229,4 kW |
| C-rate | 0,45 C |
| Demanda residual maxima | 600 kW |

## 3. Indicadores Financeiros

- CAPEX: R$ 2.038.800
- OPEX anual: R$ 20.388
- Economia anual: R$ 173.312
- Payback simples: 17 anos
- VPL (20 anos): -R$ 1.083.495 (inviavel sem revenue stacking)

## 4. Veredicto

Projeto **inviavel** so com peak shaving. Recomenda-se explorar `revenue stacking`
via migracao ACL, FV+BNDES Finem ou redimensionamento ao teto de R$ 1,5M.
""",
            "erro": None,
        },
    ]
    pdf_bytes = gerar_proposta_pdf(
        msgs,
        session_id="smoketest-1234-5678-abcd",
        modelo="claude-sonnet-4-6",
    )
    out = Path(__file__).parent / "_smoketest_proposta.pdf"
    out.write_bytes(pdf_bytes)
    print(f"PDF gerado: {out} ({len(pdf_bytes):,} bytes)")
