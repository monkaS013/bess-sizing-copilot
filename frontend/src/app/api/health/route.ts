import { NextResponse } from "next/server";

const API_URL = process.env.BESS_API_URL ?? "http://localhost:8000";

export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/health`, {
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: `Backend respondeu ${res.status}` },
        { status: res.status }
      );
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json(
      {
        error: "Backend FastAPI inacessivel.",
        detalhe: err instanceof Error ? err.message : String(err),
        api_url: API_URL,
      },
      { status: 503 }
    );
  }
}
