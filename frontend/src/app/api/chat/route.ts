import { NextResponse } from "next/server";

const API_URL = process.env.BESS_API_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Body JSON invalido." },
      { status: 400 }
    );
  }

  try {
    const res = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      {
        error: "Backend FastAPI inacessivel ao chamar /api/chat.",
        detalhe: err instanceof Error ? err.message : String(err),
      },
      { status: 503 }
    );
  }
}
