import { NextRequest, NextResponse } from "next/server";

// Server-side: use Docker service name for container-to-container communication
// Falls back to NEXT_PUBLIC_API_URL for local dev
const BACKEND_URL = process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();

    const res = await fetch(`${BACKEND_URL}/ai/analyze-image`, {
      method: "POST",
      body: formData,
    });

    // Handle non-JSON responses gracefully
    const text = await res.text();
    try {
      const data = JSON.parse(text);
      return NextResponse.json(data, { status: res.status });
    } catch {
      return NextResponse.json(
        { detail: `Backend error: ${text.substring(0, 200)}` },
        { status: res.status || 500 }
      );
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[PROXY] Analyze error:", err);
    return NextResponse.json(
      { detail: `Proxy error: ${message}` },
      { status: 502 }
    );
  }
}
