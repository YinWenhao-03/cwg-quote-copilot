"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BadgeCheck,
  Calculator,
  FilePlus2,
  MessageSquareText,
  Search,
  Upload,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { useSession } from "@/components/app-shell";
import { api } from "@/lib/api";
import type { DocumentRecord, Evidence, KnowledgeAnswer } from "@/lib/types";

const classNames: Record<string, string> = {
  public: "公开",
  sales: "销售",
  procurement: "采购",
  management: "管理层",
};

export default function KnowledgePage() {
  const user = useSession();
  const router = useRouter();
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [query, setQuery] = useState("S4-1000 的包装要求是什么");
  const [mode, setMode] = useState<"hybrid" | "dense" | "bm25">("hybrid");
  const [answer, setAnswer] = useState<KnowledgeAnswer | null>(null);
  const [tab, setTab] = useState<"documents" | "search" | "upload">("documents");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  function load() {
    api<DocumentRecord[]>("/documents").then(setDocuments).catch((error) => setMessage(error.message));
  }

  useEffect(load, []);

  async function search(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setAnswer(null);
    try {
      setAnswer(
        await api<KnowledgeAnswer>("/answer", {
          method: "POST",
          body: JSON.stringify({ query, top_k: 6, retrieval_mode: mode }),
        }),
      );
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const form = new FormData(event.currentTarget);
      await api("/documents", { method: "POST", body: form });
      setMessage("文档已进入解析队列");
      load();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function startPricing() {
    setBusy(true);
    setMessage("");
    try {
      const inquiry = await api<{ id: string }>("/inquiries", {
        method: "POST",
        body: JSON.stringify({ raw_text: query }),
      });
      const result = await api<{ quote_id?: string }>(`/inquiries/${inquiry.id}/process`, {
        method: "POST",
      });
      router.push(result.quote_id ? `/quotes/${result.quote_id}` : `/inquiries/${inquiry.id}`);
    } catch (error) {
      setMessage((error as Error).message);
      setBusy(false);
    }
  }

  const canUpload = user.role !== "sales";
  const results = answer?.evidence ?? [];

  return (
    <>
      <PageHeader eyebrow="企业知识库" title="知识问答" detail="直接回答业务问题，并保留可核验的引用依据。" />
      <div className="mb-5 flex gap-1 border-b border-[var(--line)]">
        {(
          [
            ["documents", "文档"],
            ["search", "问答"],
            ...(canUpload ? [["upload", "上传"]] : []),
          ] as Array<[typeof tab, string]>
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={`h-10 border-b-2 px-4 text-sm font-semibold ${
              tab === value
                ? "border-[var(--accent)] text-[var(--accent)]"
                : "border-transparent text-[var(--muted)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {message && (
        <div className="mb-4 bg-[#eef2f0] px-4 py-3 text-sm" style={{ borderRadius: 6 }}>
          {message}
        </div>
      )}

      {tab === "documents" && (
        <div className="table-shell">
          <table className="data-table">
            <thead>
              <tr>
                <th>文档</th>
                <th>类型</th>
                <th>密级</th>
                <th>范围</th>
                <th>当前版本</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <div className="font-semibold">{doc.title}</div>
                    <div className="mt-1 text-xs text-[var(--muted)]">{doc.sku || doc.id.slice(0, 8)}</div>
                  </td>
                  <td>{doc.document_type}</td>
                  <td>{classNames[doc.classification] || doc.classification}</td>
                  <td>{doc.customer_id || "全局"}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      V{doc.versions[0]?.version}
                      <StatusBadge status={doc.versions[0]?.status || "draft"} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "search" && (
        <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
          <form onSubmit={search} className="panel h-fit p-5">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">业务问题</span>
              <textarea
                className="field min-h-28"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <div className="mt-4">
              <span className="mb-1.5 block text-sm font-medium">检索方式</span>
              <div className="grid grid-cols-3 gap-1 bg-[#eef2f0] p-1" style={{ borderRadius: 6 }}>
                {(
                  [
                    ["hybrid", "融合"],
                    ["dense", "语义"],
                    ["bm25", "关键词"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    type="button"
                    key={value}
                    onClick={() => setMode(value)}
                    className={`h-8 text-xs font-semibold ${
                      mode === value
                        ? "bg-white text-[var(--accent)] shadow-sm"
                        : "text-[var(--muted)]"
                    }`}
                    style={{ borderRadius: 4 }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <button className="button-primary mt-4 w-full" disabled={busy}>
              <Search size={16} />
              {busy ? "正在生成答案" : "生成确切答案"}
            </button>
          </form>

          <section className="panel min-h-96 overflow-hidden">
            <div className="border-b border-[var(--line)] px-5 py-4">
              <h2 className="font-semibold">直接答案</h2>
            </div>
            {answer ? (
              <div>
                <div className="bg-[#f8faf9] p-5 sm:p-6">
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    {answer.answer_type === "grounded" || answer.answer_type === "calculated" ? (
                      <span
                        className="inline-flex items-center gap-1.5 bg-[var(--accent-soft)] px-2.5 py-1 text-xs font-semibold text-[var(--accent-dark)]"
                        style={{ borderRadius: 4 }}
                      >
                        {answer.answer_type === "calculated" ? (
                          <><Calculator size={14} /> 确定性判断</>
                        ) : (
                          <><BadgeCheck size={14} /> 已核验引用</>
                        )}
                      </span>
                    ) : (
                      <span
                        className="bg-[#f5ece5] px-2.5 py-1 text-xs font-semibold text-[#7d4d2e]"
                        style={{ borderRadius: 4 }}
                      >
                        {answer.answer_type === "requires_pricing_workflow" ? "转入报价计算" : "资料不足"}
                      </span>
                    )}
                    <span className="text-xs text-[var(--muted)]">{answer.model}</span>
                  </div>
                  <div className="whitespace-pre-wrap text-[15px] leading-7 text-[var(--ink)]">
                    {answer.answer}
                  </div>
                  {answer.answer_type === "requires_pricing_workflow" && user.role !== "procurement" && (
                    <button className="button-primary mt-4" onClick={startPricing} disabled={busy}>
                      <Calculator size={16} />
                      {busy ? "正在创建报价任务" : "开始报价计算"}
                    </button>
                  )}
                  {answer.citations.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {answer.citations.map((citation) => (
                        <a
                          key={citation.chunk_id}
                          href={`#evidence-${citation.index}`}
                          className="border border-[var(--line)] bg-white px-2.5 py-1.5 text-xs font-medium text-[var(--accent-dark)]"
                          style={{ borderRadius: 4 }}
                        >
                          [{citation.index}] {citation.title}
                          {citation.page ? ` · P${citation.page}` : ""}
                        </a>
                      ))}
                    </div>
                  )}
                </div>

                {answer.answer_type !== "requires_pricing_workflow" && results.length > 0 && (
                  <details className="border-t border-[var(--line)]">
                    <summary className="cursor-pointer px-5 py-4 text-sm font-semibold text-[var(--muted)]">
                      查看证据原文与检索轨迹（{results.length}）
                    </summary>
                    <div className="divide-y divide-[var(--line)] border-t border-[var(--line)]">
                      {results.map((item, index) => (
                        <EvidenceItem key={item.chunk_id} item={item} index={index + 1} />
                      ))}
                    </div>
                  </details>
                )}
              </div>
            ) : (
              <div className="grid min-h-80 place-items-center text-sm text-[var(--muted)]">
                <div className="text-center">
                  <MessageSquareText size={26} className="mx-auto mb-3" />
                  输入问题后获得直接答案
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {tab === "upload" && canUpload && (
        <form onSubmit={upload} className="panel max-w-3xl p-5 sm:p-6">
          <div className="mb-5 flex items-center gap-2">
            <FilePlus2 size={19} className="text-[var(--accent)]" />
            <h2 className="font-semibold">上传新版本</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label>
              <span className="mb-1.5 block text-sm font-medium">标题</span>
              <input name="title" className="field" required />
            </label>
            <label>
              <span className="mb-1.5 block text-sm font-medium">文档类型</span>
              <input name="document_type" className="field" placeholder="product_manual" required />
            </label>
            <label>
              <span className="mb-1.5 block text-sm font-medium">密级</span>
              <select name="classification" className="field">
                {user.role === "manager" && (
                  <>
                    <option value="sales">销售</option>
                    <option value="management">管理层</option>
                  </>
                )}
                <option value="public">公开</option>
                <option value="procurement">采购</option>
              </select>
            </label>
            <label>
              <span className="mb-1.5 block text-sm font-medium">SKU</span>
              <input name="sku" className="field" />
            </label>
            <label>
              <span className="mb-1.5 block text-sm font-medium">生效日期</span>
              <input name="valid_from" type="date" defaultValue="2026-08-11" className="field" required />
            </label>
            <label>
              <span className="mb-1.5 block text-sm font-medium">失效日期</span>
              <input name="valid_to" type="date" defaultValue="2027-08-11" className="field" required />
            </label>
            <label className="sm:col-span-2">
              <span className="mb-1.5 block text-sm font-medium">文件</span>
              <input
                name="file"
                type="file"
                accept=".pdf,.docx,.xlsx,.eml"
                className="field pt-2"
                required
              />
            </label>
          </div>
          <button className="button-primary mt-5" disabled={busy}>
            <Upload size={16} />
            {busy ? "上传中" : "上传并创建版本"}
          </button>
        </form>
      )}
    </>
  );
}

function EvidenceItem({ item, index }: { item: Evidence; index: number }) {
  const trace = item.metadata.retrieval || {};
  return (
    <article id={`evidence-${index}`} className="scroll-mt-20 p-5">
      <div className="flex justify-between gap-3">
        <h3 className="text-sm font-semibold">
          [{index}] {item.title}
        </h3>
        <span className="text-xs tabular-nums text-[var(--muted)]">{item.score}</span>
      </div>
      <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{item.content}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
        <span className="bg-[#eaf0f8] px-2 py-1 text-[#36577c]" style={{ borderRadius: 4 }}>
          Dense {trace.dense_rank ? `#${trace.dense_rank}` : "未命中"}
        </span>
        <span
          className="bg-[var(--accent-soft)] px-2 py-1 text-[var(--accent-dark)]"
          style={{ borderRadius: 4 }}
        >
          BM25 {trace.bm25_rank ? `#${trace.bm25_rank}` : "未命中"}
        </span>
        <span className="bg-[#f0f2f1] px-2 py-1 text-[var(--muted)]" style={{ borderRadius: 4 }}>
          RRF {trace.rrf_score ?? "-"}
        </span>
      </div>
      <div className="mt-3 text-xs text-[var(--muted)]">
        {item.metadata.embedding_model} · V{item.metadata.version} · {classNames[item.metadata.classification]} ·
        有效至 {item.metadata.valid_to}
      </div>
    </article>
  );
}
