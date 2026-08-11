import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export async function GET() {
  const token = cookies().get("cwg_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  try {
    const response = await fetch(`${backend}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    const result = new NextResponse(await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
    if (response.status === 401) {
      result.cookies.set("cwg_token", "", { httpOnly: true, maxAge: 0, path: "/" });
    }
    return result;
  } catch {
    return NextResponse.json({ detail: "工作台暂时无法连接，请稍后重试" }, { status: 503 });
  }
}
