import { ReactNode } from "react";

export function PageHeader({ eyebrow, title, detail, actions }: { eyebrow: string; title: string; detail?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <div className="eyebrow mb-1">{eyebrow}</div>
        <h1 className="page-title">{title}</h1>
        {detail && <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">{detail}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  );
}
