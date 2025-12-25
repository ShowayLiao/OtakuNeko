import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Sidebar } from "../components/layout/Sidebar";
import "./globals.css";
import { ChatProvider } from "@/contexts/ChatContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "OtakuNeko Dashboard",
  description: "AI-powered anime dashboard",
  icons: {
    icon: "/Icon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {/* 防闪烁脚本：在React加载前执行，立即应用保存的主题 */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  const savedTheme = localStorage.getItem('theme');
                  if (savedTheme) {
                    document.documentElement.setAttribute('data-theme', savedTheme);
                  }
                } catch (e) {}
              })();
            `,
          }}
        />
        <div className="flex h-screen bg-gray-50">
          <Sidebar />
          <main className="flex-1 overflow-y-auto">
            <ChatProvider>
              {children}
            </ChatProvider>
          </main>
        </div>
      </body>
    </html>
  );
}
