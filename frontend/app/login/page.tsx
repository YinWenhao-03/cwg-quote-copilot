"use client";

import { FormEvent, useState } from "react";
import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";

const accounts = [
  { role: "销售", email: "sales@cwg.local", password: "SalesDemo!2026" },
  { role: "采购", email: "procurement@cwg.local", password: "ProcDemo!2026" },
  { role: "经理", email: "manager@cwg.local", password: "ManagerDemo!2026" },
];

export default function LoginPage() {
  const [email, setEmail] = useState(accounts[0].email);
  const [password, setPassword] = useState(accounts[0].password);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch("/api/session/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        signal: controller.signal,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "登录失败");
      window.location.replace("/");
    } catch (requestError) {
      setError(requestError instanceof DOMException && requestError.name === "AbortError" ? "登录超时，请重试" : (requestError as Error).message || "登录失败");
      setLoading(false);
    } finally {
      window.clearTimeout(timeout);
    }
  }
  function choose(account: typeof accounts[number]) { setEmail(account.email); setPassword(account.password); setError(""); }
  return (
    <main className="grid min-h-screen bg-[#eef2ef] lg:grid-cols-[minmax(360px,520px)_1fr]">
      <section className="flex flex-col justify-between bg-[#17231f] p-8 text-white sm:p-12">
        <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center bg-[#28a990] text-sm font-bold" style={{ borderRadius: 6 }}>CQ</span><div><div className="font-semibold">CWG Quote Copilot</div><div className="text-xs text-white/55">企业报价决策工作台</div></div></div>
        <div className="py-16"><p className="mb-3 text-sm font-semibold text-[#5dd4bb]">从询价到可审计报价</p><h1 className="max-w-md text-4xl font-semibold leading-tight">价格由规则计算，结论由证据支撑。</h1><p className="mt-5 max-w-md text-sm leading-7 text-white/62">知识检索、当前成本、物流费率和审批权限在同一条流程中协作，模型不负责猜价格。</p></div>
        <div className="flex items-center gap-2 text-xs text-white/50"><ShieldCheck size={16} />本系统全部使用模拟企业数据</div>
      </section>
      <section className="flex items-center justify-center p-5 sm:p-10">
        <div className="w-full max-w-md">
          <div className="mb-7"><LockKeyhole className="mb-4 text-[var(--accent)]" size={28} /><h2 className="text-2xl font-semibold">登录工作台</h2><p className="mt-2 text-sm text-[var(--muted)]">选择演示身份，查看不同数据权限。</p></div>
          <div className="mb-5 grid grid-cols-3 gap-2">
            {accounts.map((account) => <button key={account.role} type="button" onClick={() => choose(account)} className={`h-10 border text-sm font-semibold ${email === account.email ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent-dark)]" : "border-[var(--line)] bg-white"}`} style={{ borderRadius: 6 }}>{account.role}</button>)}
          </div>
          <form onSubmit={submit} className="space-y-4">
            <label className="block"><span className="mb-1.5 block text-sm font-medium">邮箱</span><input className="field" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            <label className="block"><span className="mb-1.5 block text-sm font-medium">密码</span><input type="password" className="field" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            {error && <p className="text-sm text-[var(--red)]">{error}</p>}
            <button className="button-primary w-full" disabled={loading}>{loading ? "登录中..." : "进入工作台"}<ArrowRight size={17} /></button>
          </form>
        </div>
      </section>
    </main>
  );
}
