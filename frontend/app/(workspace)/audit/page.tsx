"use client";

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api, fmtDate } from "@/lib/api";

interface Event { id: string; trace_id: string; actor_user_id: string | null; action: string; resource_type: string; resource_id: string | null; detail: Record<string,any>; created_at: string; }

const actionLabels: Record<string,string> = { "inquiry.created":"创建询价", "inquiry.extracted":"解析询价", "inquiry.corrected":"人工补全", "quote.draft_generated":"生成报价草稿", "quote.submitted":"提交审批", "quote.approved":"批准报价", "quote.rejected":"驳回报价", "knowledge.searched":"知识检索", "document.indexed":"文档入库", "document.version_created":"创建文档版本", "evaluation.completed":"完成评测", "pricing.blocked":"定价阻断" };

export default function AuditPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api<Event[]>("/audit-events").then(setEvents).catch((e) => setError(e.message)); }, []);
  const filtered = useMemo(() => events.filter((event) => `${event.trace_id} ${event.action} ${event.resource_id}`.toLowerCase().includes(query.toLowerCase())), [events,query]);
  return <><PageHeader eyebrow="安全与合规" title="审计追踪" detail="检索、定价、状态变化、审批和 PDF 固化共享 Trace ID。" actions={<div className="relative"><Search className="absolute left-3 top-3 text-[var(--muted)]" size={15}/><input className="field w-64 pl-9" placeholder="搜索 Trace ID" value={query} onChange={(e) => setQuery(e.target.value)}/></div>} />
    {error && <p className="mb-4 text-sm text-[var(--red)]">{error}</p>}
    <div className="table-shell"><table className="data-table"><thead><tr><th>时间</th><th>事件</th><th>Trace ID</th><th>资源</th><th>详情</th></tr></thead><tbody>{filtered.map((event) => <tr key={event.id}><td className="whitespace-nowrap text-[var(--muted)]">{fmtDate(event.created_at)}</td><td className="font-semibold">{actionLabels[event.action] || event.action}</td><td className="font-mono text-xs">{event.trace_id.slice(0,13)}...</td><td>{event.resource_type}<div className="mt-1 font-mono text-[11px] text-[var(--muted)]">{event.resource_id?.slice(0,10) || '-'}</div></td><td className="max-w-sm truncate font-mono text-xs text-[var(--muted)]">{JSON.stringify(event.detail)}</td></tr>)}</tbody></table></div>
  </>;
}
