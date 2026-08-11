import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CWG Quote Copilot",
  description: "企业询价与报价审批工作台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
