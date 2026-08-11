"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CheckCircle2, Inbox, Loader2, MailOpen } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api, fmtDate } from "@/lib/api";
import type { InboxMessage } from "@/lib/types";

export default function InboxPage() {
  const [messages, setMessages] = useState<InboxMessage[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  useEffect(() => { api<InboxMessage[]>("/inbox").then((items) => { setMessages(items); setSelectedId(items[0]?.id || null); }).catch((e) => setError(e.message)); }, []);
  const selected = useMemo(() => messages.find((item) => item.id === selectedId), [messages, selectedId]);
  async function createInquiry() {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      const inquiry = await api<{ id: string }>("/inquiries", { method: "POST", body: JSON.stringify({ raw_text: selected.body, inbox_message_id: selected.id }) });
      const result = await api<{ status: string; quote_id?: string }>(`/inquiries/${inquiry.id}/process`, { method: "POST" });
      router.push(result.quote_id ? `/quotes/${result.quote_id}` : `/inquiries/${inquiry.id}`);
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }
  return (
    <>
      <PageHeader eyebrow="客户入口" title="询价收件箱" detail="从模拟邮件创建询价，结构化结果会在进入定价前接受必填校验。" />
      {error && <div className="mb-4 border border-[#f2caca] bg-[var(--red-soft)] px-4 py-3 text-sm text-[var(--red)]" style={{ borderRadius: 6 }}>{error}</div>}
      <div className="panel grid min-h-[620px] overflow-hidden lg:grid-cols-[390px_1fr]">
        <div className="border-b border-[var(--line)] lg:border-b-0 lg:border-r">
          <div className="flex h-14 items-center justify-between border-b border-[var(--line)] px-4"><span className="text-sm font-semibold">全部邮件</span><span className="text-xs text-[var(--muted)]">{messages.length} 封</span></div>
          <div className="max-h-[565px] overflow-y-auto">
            {messages.map((message) => <button key={message.id} onClick={() => setSelectedId(message.id)} className={`block w-full border-b border-[#edf1ef] p-4 text-left transition ${selectedId === message.id ? "bg-[var(--accent-soft)]" : "hover:bg-[#f8faf9]"}`}><div className="flex items-start justify-between gap-3"><span className="truncate text-sm font-semibold">{message.sender}</span><span className="shrink-0 text-[11px] text-[var(--muted)]">{fmtDate(message.received_at)}</span></div><div className="mt-1 truncate text-sm">{message.subject}</div><div className="mt-2 flex items-center gap-1.5 text-xs text-[var(--muted)]">{message.processed ? <CheckCircle2 size={13} className="text-[var(--accent)]" /> : <Inbox size={13} />}{message.processed ? "已转为询价" : "待处理"}</div></button>)}
          </div>
        </div>
        <div className="flex min-w-0 flex-col">
          {selected ? <><div className="border-b border-[var(--line)] p-5 sm:p-6"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div><div className="mb-2 flex items-center gap-2 text-xs text-[var(--muted)]"><MailOpen size={14} />{selected.sender}</div><h2 className="text-lg font-semibold">{selected.subject}</h2><p className="mt-1 text-xs text-[var(--muted)]">客户范围：{selected.customer_id || "待识别"}</p></div><button className="button-primary shrink-0" onClick={createInquiry} disabled={busy}>{busy ? <Loader2 size={17} className="animate-spin" /> : <ArrowRight size={17} />}{busy ? "正在解析" : "创建并解析询价"}</button></div></div><article className="whitespace-pre-wrap p-5 text-sm leading-7 sm:p-7">{selected.body}</article></> : <div className="grid flex-1 place-items-center text-sm text-[var(--muted)]">收件箱为空</div>}
        </div>
      </div>
    </>
  );
}
