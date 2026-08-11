"use client";

import { useEffect, useState } from "react";
import { Activity, Play, ShieldCheck, TimerReset } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api, fmtDate } from "@/lib/api";

interface EvalRun { id: string; status: string; metrics: Record<string, number>; created_at: string; completed_at: string | null; }

const metricLabels: Record<string,string> = { recall_at_5: "Recall@5", recall_at_10: "Recall@10", hit_at_5: "Hit@5", exact_sku_hit_at_5: "精确 SKU Hit@5", mrr: "MRR", ndcg_at_5: "nDCG@5", citation_accuracy: "引用准确率", unauthorized_exposure_rate: "越权暴露率", expired_usage_rate: "过期资料率" };

export default function EvalsPage() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function load() { api<EvalRun[]>("/eval-runs").then(setRuns).catch((e) => setError(e.message)); }
  useEffect(load, []);
  async function run() { setBusy(true); setError(""); try { await api("/eval-runs", { method: "POST" }); load(); } catch(e) { setError((e as Error).message); } finally { setBusy(false); } }
  const latest = runs[0];
  return <><PageHeader eyebrow="质量门禁" title="RAG 评测" detail="固定 100 条标注问题，分别验证召回、排序、有效期和销售权限隔离。" actions={<button className="button-primary" onClick={run} disabled={busy}><Play size={16}/>{busy ? "评测中" : "运行评测"}</button>} />
    {error && <p className="mb-4 text-sm text-[var(--red)]">{error}</p>}
    {latest ? <><section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Object.entries(latest.metrics).filter(([key]) => key !== 'case_count').map(([key,value]) => { const isRisk = key.includes('rate'); const pass = isRisk ? value === 0 : key === 'recall_at_10' ? value >= .9 : value >= .8; return <div className="panel p-5" key={key}><div className="mb-4 flex items-center justify-between"><span className="text-xs font-semibold text-[var(--muted)]">{metricLabels[key] || key}</span>{pass ? <ShieldCheck size={16} className="text-[var(--accent)]"/> : <Activity size={16} className="text-[var(--amber)]"/>}</div><div className="text-2xl font-semibold tabular-nums">{(value * 100).toFixed(1)}%</div><div className="mt-2 h-1.5 overflow-hidden bg-[#e8ecea]" style={{ borderRadius: 3 }}><div className={isRisk ? "h-full bg-[var(--red)]" : "h-full bg-[var(--accent)]"} style={{ width: `${Math.min(value * 100,100)}%` }} /></div></div>})}</section>
      <div className="mt-6 table-shell"><table className="data-table"><thead><tr><th>评测批次</th><th>样本数</th><th>Recall@10</th><th>Hit@5</th><th>越权暴露</th><th>完成时间</th></tr></thead><tbody>{runs.map((item) => <tr key={item.id}><td className="font-mono text-xs">{item.id}</td><td>{item.metrics.case_count}</td><td>{(item.metrics.recall_at_10*100).toFixed(1)}%</td><td>{(item.metrics.hit_at_5*100).toFixed(1)}%</td><td>{(item.metrics.unauthorized_exposure_rate*100).toFixed(2)}%</td><td>{fmtDate(item.completed_at)}</td></tr>)}</tbody></table></div></> : <div className="panel grid min-h-96 place-items-center text-sm text-[var(--muted)]"><div className="text-center"><TimerReset className="mx-auto mb-3" size={25}/><p>尚未运行评测</p></div></div>}
  </>;
}
