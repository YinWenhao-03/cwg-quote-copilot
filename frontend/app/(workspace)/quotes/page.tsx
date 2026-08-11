"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ReceiptText } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, fmtDate, money } from "@/lib/api";
import type { Quote } from "@/lib/types";

export default function QuotesPage() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { api<Quote[]>("/quotes").then(setQuotes).catch((e) => setError(e.message)); }, []);
  return <><PageHeader eyebrow="报价管理" title="报价工作台" detail="查看建议价格、审批状态、证据来源与固化版本。" />
    {error && <p className="mb-4 text-sm text-[var(--red)]">{error}</p>}
    <div className="table-shell"><table className="data-table"><thead><tr><th>产品 / 客户</th><th>数量</th><th>建议单价</th><th>版本</th><th>状态</th><th>创建时间</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>
      {quotes.map((quote) => <tr key={quote.id}><td><div className="font-semibold">{quote.public_json.sku}</div><div className="mt-1 text-xs text-[var(--muted)]">{quote.public_json.customer_name}</div></td><td>{quote.quantity.toLocaleString("zh-CN")}</td><td className="font-semibold tabular-nums">{money(quote.proposed_unit_price, quote.currency)}</td><td>V{quote.version}</td><td><StatusBadge status={quote.status} /></td><td className="text-[var(--muted)]">{fmtDate(quote.created_at)}</td><td><Link href={`/quotes/${quote.id}`} className="grid h-8 w-8 place-items-center text-[var(--accent)]" title="查看报价"><ArrowUpRight size={17} /></Link></td></tr>)}
      {!quotes.length && <tr><td colSpan={7}><div className="grid min-h-56 place-items-center text-sm text-[var(--muted)]"><div className="text-center"><ReceiptText className="mx-auto mb-3" size={24} />暂无报价草稿</div></div></td></tr>}
    </tbody></table></div>
  </>;
}
