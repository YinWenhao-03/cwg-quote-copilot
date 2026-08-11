import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

async function proxy(request: NextRequest, { params }: { params: { path: string[] } }) {
  const token = cookies().get("cwg_token")?.value;
  if (!token) return NextResponse.json({ detail: "请先登录" }, { status: 401 });
  const target = `${backend}/${params.path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers();
  headers.set("Authorization", `Bearer ${token}`);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const response = await fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
    cache: "no-store",
  });
  const outputHeaders = new Headers();
  for (const name of ["content-type", "content-disposition"]) {
    const value = response.headers.get(name);
    if (value) outputHeaders.set(name, value);
  }
  return new NextResponse(response.body, { status: response.status, headers: outputHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
