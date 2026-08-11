import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export async function GET() {
  const token = cookies().get("cwg_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  const response = await fetch(`${backend}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
