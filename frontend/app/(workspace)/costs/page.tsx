"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, money } from "@/lib/api";

interface Cost { id: string; sku: string; supplier: string; unit_cost: string; currency: string; valid_from: string; valid_to: string; status: string; }

export default function CostsPage() {
  const [costs, setCosts] = useState<Cost[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { api<Cost[]>("/supplier-costs").then(setCosts).catch((e) => setError(e.message)); }, []);
  return <><PageHeader eyebrow="结构化事实源" title="供应商成本" detail="定价引擎只读取当前有效且已批准的记录；过期价格保留审计但不进入计算。" />
    {error && <p className="mb-4 text-sm text-[var(--red)]">{error}</p>}
    <div className="table-shell"><table className="data-table"><thead><tr><th>SKU</th><th>供应商</th><th>单位成本</th><th>有效期</th><th>状态</th></tr></thead><tbody>{costs.map((cost) => <tr key={cost.id} className={cost.status === 'expired' ? 'text-[var(--muted)]' : ''}><td className="font-semibold">{cost.sku}</td><td>{cost.supplier}</td><td className="font-semibold tabular-nums">{money(cost.unit_cost,cost.currency)}</td><td>{cost.valid_from} 至 {cost.valid_to}</td><td><StatusBadge status={cost.status} /></td></tr>)}</tbody></table></div>
  </>;
}
