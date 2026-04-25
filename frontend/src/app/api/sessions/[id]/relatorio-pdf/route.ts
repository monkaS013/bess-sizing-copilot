import { NextResponse } from "next/server";

const API_URL = process.env.BESS_API_URL ?? "http://localhost:8000";

/**
 * Proxy para POST /api/sessions/{id}/relatorio-pdf no FastAPI.
 * Retransmite o PDF binario com o Content-Disposition do backend.
 */
export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const { id } = await context.params;

  if (!id) {
    return NextResponse.json(
      { error: "Session ID ausente na URL." },
      { status: 400 }
    );
  }

  try {
    const res = await fetch(
      `${API_URL}/api/sessions/${id}/relatorio-pdf`,
      {
        method: "POST",
        cache: "no-store",
      }
    );

    if (!res.ok) {
      // Backend respondeu erro (404, 400, 500). Repasse JSON do detalhe.
      const text = await res.text();
      let detalhe: string = text;
      try {
        const json = JSON.parse(text) as { detail?: string };
        detalhe = json.detail ?? text;
      } catch {
        // mantem text bruto
      }
      return NextResponse.json(
        { error: detalhe },
        { status: res.status }
      );
    }

    const arrayBuffer = await res.arrayBuffer();
    const filename =
      res.headers.get("X-Filename") ??
      res.headers
        .get("Content-Disposition")
        ?.match(/filename="?([^"]+)"?/)?.[1] ??
      `BESS_Proposta_${id.slice(0, 8)}.pdf`;

    return new Response(arrayBuffer, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="${filename}"`,
        "X-Filename": filename,
      },
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: "Backend FastAPI inacessivel ao gerar PDF.",
        detalhe: err instanceof Error ? err.message : String(err),
      },
      { status: 503 }
    );
  }
}
