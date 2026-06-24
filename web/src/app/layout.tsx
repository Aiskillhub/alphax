import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AlphaX — Agent Economy Protocol",
  description: "不是又一个 AI 工具。是 Agent 之间发现、交易、进化的底层协议。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh" className="h-full">
      <body className="min-h-full bg-[#050510] text-[#e8e8f0] antialiased">
        {children}
      </body>
    </html>
  );
}
