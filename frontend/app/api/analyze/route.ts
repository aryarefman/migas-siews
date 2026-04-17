import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();

    const res = await fetch(`${API_URL}/ai/analyze-image`, {
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
  } catch (err: any) {
    console.error("[PROXY] Analyze error:", err);
    return NextResponse.json(
      { detail: `Proxy error: ${err.message}` },
      { status: 502 }
    );
  }
}
