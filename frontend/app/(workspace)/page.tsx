"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, CircleDollarSign, FileCheck2, Inbox, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";

interface Dashboard { inquiries: number; quotes: number; pending_approvals: number; documents: number; chunks: number; role: string; embedding_provider: string; embedding_model: string; }

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  useEffect(() => { api<Dashboard>("/dashboard").then(setData).catch(() => undefined); }, []);
  const metrics = [
    { label: "已接收询价", value: data?.inquiries ?? "-", icon: Inbox, tone: "text-[#36577c] bg-[#eaf0f8]" },
    { label: "报价草稿", value: data?.quotes ?? "-", icon: CircleDollarSign, tone: "text-[#087f6d] bg-[#e5f4f0]" },
    { label: "待经理审批", value: data?.pending_approvals ?? "-", icon: FileCheck2, tone: "text-[#a96208] bg-[#fff3db]" },
    { label: "有效知识文档", value: data?.documents ?? "-", icon: BookOpen, tone: "text-[#73538f] bg-[#f1eaf7]" },
  ];
  return (
    <>
      <PageHeader eyebrow="业务总览" title="报价决策中心" detail="集中查看询价流转、报价审批和知识库运行状态。" />
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(({ label, value, icon: Icon, tone }) => <div key={label} className="panel p-5"><div className={`mb-5 grid h-9 w-9 place-items-center ${tone}`} style={{ borderRadius: 6 }}><Icon size={18} /></div><div className="text-3xl font-semibold tabular-nums">{value}</div><div className="mt-1 text-sm text-[var(--muted)]">{label}</div></div>)}
      </section>
      <section className="mt-7 grid gap-5 xl:grid-cols-[1.25fr_.75fr]">
        <div className="panel overflow-hidden">
          <div className="border-b border-[var(--line)] px-5 py-4"><h2 className="font-semibold">标准报价流程</h2><p className="mt-1 text-xs text-[var(--muted)]">系统在缺少关键字段时暂停，不让模型自行补全。</p></div>
          <div className="grid gap-px bg-[var(--line)] sm:grid-cols-2">
            {[['01','解析询价','模型只负责读取邮件中的产品、数量、包装和交付信息。'],['02','核验事实','产品、成本、物流和汇率均通过确定性数据查询。'],['03','计算价格','Decimal 规则引擎计算到岸成本、标准价和硬底价。'],['04','经理审批','批准后固化版本并生成客户可见 PDF。']].map(([no,title,text]) => <div key={no} className="bg-white p-5"><span className="text-xs font-bold text-[var(--accent)]">{no}</span><h3 className="mt-3 text-sm font-semibold">{title}</h3><p className="mt-1 text-xs leading-5 text-[var(--muted)]">{text}</p></div>)}
          </div>
        </div>
        <div className="panel p-5">
          <div className="mb-5 flex items-center gap-2"><ShieldCheck size={19} className="text-[var(--accent)]" /><h2 className="font-semibold">运行边界</h2></div>
          <dl className="space-y-4 text-sm">
            <div className="flex justify-between gap-4 border-b border-[var(--line)] pb-3"><dt className="text-[var(--muted)]">融合检索</dt><dd className="text-right font-medium">BM25 + {data?.embedding_provider === 'ollama' ? 'Ollama' : '本地向量'}</dd></div>
            <div className="flex justify-between gap-4 border-b border-[var(--line)] pb-3"><dt className="text-[var(--muted)]">Embedding</dt><dd className="max-w-[190px] truncate text-right font-medium" title={data?.embedding_model}>{data?.embedding_model || '-'}</dd></div>
            <div className="flex justify-between gap-4 border-b border-[var(--line)] pb-3"><dt className="text-[var(--muted)]">索引规模</dt><dd className="font-medium">{data?.chunks ?? "-"} Chunks</dd></div>
            <div className="flex justify-between gap-4 border-b border-[var(--line)] pb-3"><dt className="text-[var(--muted)]">外发动作</dt><dd className="font-medium">仅生成草稿</dd></div>
          </dl>
          <Link href="/quotes" className="button-secondary mt-6 w-full">进入报价工作台<ArrowRight size={16} /></Link>
        </div>
      </section>
    </>
  );
}
