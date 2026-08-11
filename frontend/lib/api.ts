export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/backend${path}`, { ...options, headers, cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(payload.detail || "请求失败");
  }
  return response.json() as Promise<T>;
}

export function fmtDate(value?: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

export function money(value: string | number | undefined, currency = "CNY") {
  if (value === undefined) return "-";
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(value));
}
