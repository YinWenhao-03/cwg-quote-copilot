import { NextRequest, NextResponse } from "next/server";

const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export async function POST(request: NextRequest) {
  const response = await fetch(`${backend}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
    cache: "no-store",
  });
  const payload = await response.json();
  if (!response.ok) return NextResponse.json(payload, { status: response.status });
  const result = NextResponse.json({ user: payload.user });
  result.cookies.set("cwg_token", payload.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 60 * 8,
    path: "/",
  });
  return result;
}
