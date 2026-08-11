"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api } from "@/lib/api";
import type { Inquiry } from "@/lib/types";

const names: Record<string, string> = { customer_id: "客户", destination: "目的地", incoterm: "贸易条款", currency: "币种", sku: "SKU", quantity: "数量", packaging: "包装" };

export default function InquiryPage() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<Inquiry | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  useEffect(() => { api<Inquiry>(`/inquiries/${id}`).then((data) => { setItem(data); const extracted = data.extracted_json || {}; const first = extracted.items?.[0] || {}; setForm({ customer_id: extracted.customer_id || "", destination: extracted.destination || "", incoterm: extracted.incoterm || "", currency: extracted.currency || "", sku: first.sku || "", quantity: first.quantity || "", packaging: first.packaging || "" }); }).catch((e) => setError(e.message)); }, [id]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api(`/inquiries/${id}`, { method: "PATCH", body: JSON.stringify({ ...form, quantity: Number(form.quantity) }) });
      const result = await api<{ status: string; quote_id?: string; error?: string }>(`/inquiries/${id}/process`, { method: "POST" });
      if (result.quote_id) router.push(`/quotes/${result.quote_id}`); else { setError(result.error || "仍有字段需要确认"); setBusy(false); }
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }
  if (!item) return <div className="text-sm text-[var(--muted)]">正在读取询价...</div>;
  return <><PageHeader eyebrow="询价校验" title="补全结构化信息" detail={`Trace ID: ${item.trace_id}`} actions={<StatusBadge status={item.status} />} />
    <div className="grid gap-5 xl:grid-cols-[.8fr_1.2fr]">
      <section className="panel p-5"><h2 className="mb-3 text-sm font-semibold">客户原文</h2><p className="whitespace-pre-wrap text-sm leading-7 text-[var(--muted)]">{item.raw_text}</p></section>
      <section className="panel p-5 sm:p-6"><div className="mb-5 flex items-start gap-3 border-b border-[var(--line)] pb-4"><AlertTriangle className="mt-0.5 shrink-0 text-[var(--amber)]" size={19} /><div><h2 className="text-sm font-semibold">需要人工确认</h2><p className="mt-1 text-xs text-[var(--muted)]">缺失字段：{item.missing_fields.map((field) => names[field] || field).join("、") || "无"}</p></div></div>
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          {[['customer_id','客户编号'],['sku','产品 SKU'],['quantity','数量'],['packaging','包装'],['destination','目的地'],['incoterm','贸易条款'],['currency','币种']].map(([key,label]) => <label key={key} className="block"><span className="mb-1.5 block text-sm font-medium">{label}</span><input className="field" value={form[key] || ""} onChange={(e) => setForm({ ...form, [key]: e.target.value })} /></label>)}
          {error && <p className="text-sm text-[var(--red)] sm:col-span-2">{error}</p>}
          <div className="sm:col-span-2"><button className="button-primary" disabled={busy}>{busy ? <Loader2 size={17} className="animate-spin" /> : <ArrowRight size={17} />}{busy ? "继续处理" : "保存并继续报价"}</button></div>
        </form>
      </section>
    </div>
  </>;
}
