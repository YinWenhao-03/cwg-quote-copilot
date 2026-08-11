"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  BarChart3,
  BookOpen,
  ChevronLeft,
  ClipboardCheck,
  FileClock,
  Inbox,
  LayoutDashboard,
  LogOut,
  Menu,
  ReceiptText,
  ShieldCheck,
  Truck,
  X,
} from "lucide-react";
import type { Role, User } from "@/lib/types";

const SessionContext = createContext<User | null>(null);
export function useSession() {
  const user = useContext(SessionContext);
  if (!user) throw new Error("Session is not ready");
  return user;
}

const navigation: Array<{
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  roles: Role[];
}> = [
  { href: "/", label: "总览", icon: LayoutDashboard, roles: ["sales", "procurement", "manager"] },
  { href: "/inbox", label: "询价收件箱", icon: Inbox, roles: ["sales", "manager"] },
  { href: "/quotes", label: "报价工作台", icon: ReceiptText, roles: ["sales", "procurement", "manager"] },
  { href: "/knowledge", label: "企业知识库", icon: BookOpen, roles: ["sales", "procurement", "manager"] },
  { href: "/costs", label: "成本与物流", icon: Truck, roles: ["procurement", "manager"] },
  { href: "/evals", label: "RAG 评测", icon: BarChart3, roles: ["manager"] },
  { href: "/audit", label: "权限审计", icon: ShieldCheck, roles: ["manager"] },
];

const roleLabels: Record<Role, string> = { sales: "销售", procurement: "采购", manager: "经理" };

export function AppShell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    fetch("/api/session/me", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        setUser(await response.json());
      })
      .catch(() => router.replace("/login"));
  }, [router]);
  const items = useMemo(() => navigation.filter((item) => user && item.roles.includes(user.role)), [user]);
  async function logout() {
    await fetch("/api/session/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }
  if (!user) return <div className="grid min-h-screen place-items-center text-sm text-[var(--muted)]">正在进入工作台...</div>;
  return (
    <SessionContext.Provider value={user}>
      <div className="min-h-screen lg:grid lg:grid-cols-[244px_1fr]">
        {open && <button aria-label="关闭导航遮罩" className="fixed inset-0 z-30 bg-black/20 lg:hidden" onClick={() => setOpen(false)} />}
        <aside className={`fixed inset-y-0 left-0 z-40 flex w-[244px] flex-col border-r border-[#24332e] bg-[#17231f] text-white transition-transform lg:sticky lg:top-0 lg:h-screen ${open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
          <div className="flex h-16 items-center justify-between border-b border-white/10 px-5">
            <Link href="/" className="flex items-center gap-3" onClick={() => setOpen(false)}>
              <span className="grid h-8 w-8 place-items-center bg-[#28a990] text-xs font-bold" style={{ borderRadius: 5 }}>CQ</span>
              <div><div className="text-sm font-semibold">CWG Quote Copilot</div><div className="text-[11px] text-white/55">报价决策工作台</div></div>
            </Link>
            <button className="lg:hidden" onClick={() => setOpen(false)} aria-label="关闭导航"><X size={19} /></button>
          </div>
          <nav className="flex-1 space-y-1 px-3 py-5">
            {items.map((item) => {
              const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              const Icon = item.icon;
              return <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className={`flex h-10 items-center gap-3 px-3 text-sm transition ${active ? "bg-white/12 text-white" : "text-white/65 hover:bg-white/7 hover:text-white"}`} style={{ borderRadius: 6 }}><Icon size={18} />{item.label}</Link>;
            })}
          </nav>
          <div className="border-t border-white/10 p-4">
            <div className="mb-3 flex items-center gap-3">
              <div className="grid h-9 w-9 place-items-center bg-white/10 text-xs font-semibold" style={{ borderRadius: 6 }}>{user.display_name.slice(0, 1)}</div>
              <div className="min-w-0"><div className="truncate text-sm font-medium">{user.display_name}</div><div className="text-xs text-white/55">{roleLabels[user.role]}权限</div></div>
            </div>
            <button onClick={logout} className="flex h-9 w-full items-center gap-2 px-2 text-sm text-white/65 hover:bg-white/7 hover:text-white" style={{ borderRadius: 6 }}><LogOut size={16} />退出登录</button>
          </div>
        </aside>
        <div className="min-w-0">
          <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-[var(--line)] bg-white/95 px-4 backdrop-blur sm:px-7 lg:px-9">
            <button onClick={() => setOpen(true)} className="grid h-9 w-9 place-items-center lg:hidden" aria-label="打开导航"><Menu size={21} /></button>
            <div className="hidden items-center gap-2 text-xs text-[var(--muted)] lg:flex"><ClipboardCheck size={15} className="text-[var(--accent)]" />所有报价须经理审批后方可导出</div>
            <div className="flex items-center gap-2 text-xs text-[var(--muted)]"><FileClock size={15} />模拟环境</div>
          </header>
          <main className="mx-auto w-full max-w-[1440px] p-4 sm:p-7 lg:p-9">{children}</main>
        </div>
      </div>
    </SessionContext.Provider>
  );
}
