"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AlertTriangle, Check, Download, ExternalLink, FileText, Send, ShieldAlert, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { useSession } from "@/components/app-shell";
import { api, money } from "@/lib/api";
import type { Quote } from "@/lib/types";

export default function QuoteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const user = useSession();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [price, setPrice] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load() { try { const data = await api<Quote>(`/quotes/${id}`); setQuote(data); setPrice(String(data.proposed_unit_price)); } catch (e) { setError((e as Error).message); } }
  useEffect(() => { load(); }, [id]);
  async function submit() { setBusy(true); setError(""); try { await api(`/quotes/${id}/submit`, { method: "POST", body: JSON.stringify({ proposed_unit_price: price }) }); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }
  async function decide(decision: "approved" | "rejected") { setBusy(true); setError(""); try { await api(`/quotes/${id}/approve`, { method: "POST", body: JSON.stringify({ decision, reason: reason || null, approved_price: price }) }); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }
  if (!quote) return <div className="text-sm text-[var(--muted)]">正在读取报价...</div>;
  const pub = quote.public_json;
  const internal = quote.internal_json;
  return <><PageHeader eyebrow={`报价版本 V${quote.version}`} title={`${pub.sku} / ${pub.customer_name}`} detail={`报价编号 ${quote.id}`} actions={<StatusBadge status={quote.status} />} />
    {error && <div className="mb-4 border border-[#f2caca] bg-[var(--red-soft)] px-4 py-3 text-sm text-[var(--red)]" style={{ borderRadius: 6 }}>{error}</div>}
    {quote.risk_flags.map((flag) => <div key={flag} className="mb-4 flex items-center gap-2 border border-[#edd29f] bg-[var(--amber-soft)] px-4 py-3 text-sm text-[#7d4b0b]" style={{ borderRadius: 6 }}><AlertTriangle size={17} />{flag}</div>)}
    <div className="grid gap-5 xl:grid-cols-[1.15fr_.85fr]">
      <div className="space-y-5">
        <section className="panel overflow-hidden"><div className="border-b border-[var(--line)] px-5 py-4"><h2 className="font-semibold">客户可见报价</h2></div><div className="grid gap-px bg-[var(--line)] sm:grid-cols-3">
          {[['产品',pub.sku],['数量',quote.quantity.toLocaleString('zh-CN')],['建议单价',money(quote.proposed_unit_price,quote.currency)],['贸易条款',pub.incoterm],['目的地',pub.destination],['交付日期',pub.requested_delivery_date || '待订单确认']].map(([label,value]) => <div key={label} className="bg-white p-4"><div className="text-xs text-[var(--muted)]">{label}</div><div className="mt-2 text-sm font-semibold">{value}</div></div>)}
        </div></section>
        <section className="panel p-5"><div className="mb-4 flex items-center gap-2"><FileText size={18} className="text-[var(--accent)]" /><h2 className="font-semibold">报价函草稿</h2></div><div className="whitespace-pre-wrap border-l-2 border-[var(--accent)] pl-4 text-sm leading-7 text-[var(--muted)]">{quote.draft_text}</div></section>
        <section className="panel overflow-hidden"><div className="border-b border-[var(--line)] px-5 py-4"><h2 className="font-semibold">证据引用</h2><p className="mt-1 text-xs text-[var(--muted)]">每条结论保留文档版本、有效期和 Chunk 标识。</p></div><div className="divide-y divide-[var(--line)]">
          {quote.evidence_json.map((evidence, index) => <div key={evidence.chunk_id} className="p-5"><div className="flex items-start justify-between gap-3"><div><div className="text-sm font-semibold">[{index + 1}] {evidence.title}</div><div className="mt-1 text-xs text-[var(--muted)]">V{evidence.metadata.version} · 有效至 {evidence.metadata.valid_to} · 得分 {evidence.score}</div></div><ExternalLink size={15} className="shrink-0 text-[var(--muted)]" /></div><p className="mt-3 line-clamp-3 text-sm leading-6 text-[var(--muted)]">{evidence.content}</p></div>)}
        </div></section>
      </div>
      <div className="space-y-5">
        <section className="panel p-5"><h2 className="mb-4 font-semibold">价格与审批</h2><label className="block"><span className="mb-1.5 block text-sm font-medium">提交单价（{quote.currency}）</span><input className="field tabular-nums" type="number" step="0.01" value={price} onChange={(e) => setPrice(e.target.value)} disabled={quote.status === 'approved'} /></label>
          {quote.status === 'draft' && user.role !== 'procurement' && <button className="button-primary mt-4 w-full" onClick={submit} disabled={busy}><Send size={16} />提交经理审批</button>}
          {quote.status === 'pending_approval' && user.role === 'manager' && <div className="mt-4 space-y-3"><textarea className="field" placeholder="例外报价或驳回时填写审批理由" value={reason} onChange={(e) => setReason(e.target.value)} /><div className="grid grid-cols-2 gap-2"><button className="button-danger" onClick={() => decide('rejected')} disabled={busy}><X size={16} />驳回</button><button className="button-primary" onClick={() => decide('approved')} disabled={busy}><Check size={16} />批准</button></div></div>}
          {quote.status === 'approved' && <a className="button-primary mt-4 w-full" href={`/api/backend/quotes/${id}/pdf`}><Download size={16} />下载最终 PDF</a>}
        </section>
        {internal && <section className="panel overflow-hidden"><div className="border-b border-[var(--line)] bg-[#fff9ed] px-5 py-4"><div className="flex items-center gap-2"><ShieldAlert size={18} className="text-[var(--amber)]" /><h2 className="font-semibold">内部价格分析</h2></div><p className="mt-1 text-xs text-[var(--muted)]">此区域不会进入客户报价或销售模型上下文。</p></div><dl className="divide-y divide-[var(--line)] text-sm">
          {internal.landed_cost && <div className="flex justify-between gap-4 px-5 py-3"><dt className="text-[var(--muted)]">到岸成本</dt><dd className="font-semibold">{money(internal.landed_cost,quote.currency)}</dd></div>}
          {internal.standard_minimum && <div className="flex justify-between gap-4 px-5 py-3"><dt className="text-[var(--muted)]">标准最低价</dt><dd className="font-semibold">{money(internal.standard_minimum,quote.currency)}</dd></div>}
          {internal.hard_floor && <div className="flex justify-between gap-4 px-5 py-3"><dt className="text-[var(--muted)]">硬底价</dt><dd className="font-semibold text-[var(--red)]">{money(internal.hard_floor,quote.currency)}</dd></div>}
          {internal.supplier && <div className="flex justify-between gap-4 px-5 py-3"><dt className="text-[var(--muted)]">成本来源</dt><dd className="font-medium">{internal.supplier}</dd></div>}
          {internal.as_of && <div className="flex justify-between gap-4 px-5 py-3"><dt className="text-[var(--muted)]">计算基准日</dt><dd>{internal.as_of}</dd></div>}
        </dl></section>}
      </div>
    </div>
  </>;
}
