import { NextResponse } from "next/server";

const API_URL = process.env.BESS_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const userId = request.headers.get("x-user-id");
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-Id"] = userId;

  try {
    const res = await fetch(`${API_URL}/api/sessions`, {
      method: "POST",
      headers,
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      {
        error: "Falha ao criar sessao.",
        detalhe: err instanceof Error ? err.message : String(err),
      },
      { status: 503 }
    );
  }
}
