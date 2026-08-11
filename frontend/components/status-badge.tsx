const styles: Record<string, string> = {
  approved: "bg-[#e5f4f0] text-[#056354]",
  completed: "bg-[#e5f4f0] text-[#056354]",
  pending_approval: "bg-[#fff3db] text-[#8b5105]",
  needs_clarification: "bg-[#fff3db] text-[#8b5105]",
  needs_product_resolution: "bg-[#fff3db] text-[#8b5105]",
  blocked: "bg-[#fdecec] text-[#9e3030]",
  rejected: "bg-[#fdecec] text-[#9e3030]",
  expired: "bg-[#f0f2f1] text-[#63706a]",
  superseded: "bg-[#f0f2f1] text-[#63706a]",
  draft: "bg-[#eaf0f8] text-[#36577c]",
  pricing: "bg-[#eaf0f8] text-[#36577c]",
};

const labels: Record<string, string> = {
  approved: "已批准",
  completed: "已完成",
  pending_approval: "待审批",
  needs_clarification: "待补充",
  needs_product_resolution: "待确认产品",
  blocked: "已阻断",
  rejected: "已驳回",
  expired: "已过期",
  superseded: "旧版本",
  draft: "草稿",
  pricing: "报价中",
  received: "已接收",
  extracting: "解析中",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex whitespace-nowrap px-2 py-1 text-xs font-semibold ${styles[status] || "bg-[#f0f2f1] text-[#52605a]"}`} style={{ borderRadius: 4 }}>
      {labels[status] || status}
    </span>
  );
}
