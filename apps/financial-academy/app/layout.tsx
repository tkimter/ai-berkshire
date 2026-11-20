import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "복리학당 · 한 회사를 제대로 읽기",
  description: "12개 장의 실적 읽기 강의, 인터랙티브 실험실, 수료 도전. 재무 숫자에서 독립적인 판단으로.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="antialiased">{children}</body>
    </html>
  );
}
