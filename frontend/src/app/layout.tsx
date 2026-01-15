import type { Metadata } from "next";
import { Sidebar } from "../components/layout/Sidebar";
import { Header } from "../components/layout/Header";
import { HeaderProvider } from "@/contexts/HeaderContext";
import "./globals.css";
import { ChatProvider } from "@/contexts/ChatContext";
import { SettingsProvider } from "@/contexts/SettingsContext";
import { ToastProvider } from "@/components/ui/Toast";

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
      <body className="antialiased">
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
          <div className="flex-1 flex flex-col overflow-hidden">
            <SettingsProvider>
              <ToastProvider>
                <ChatProvider>
                  <HeaderProvider>
                    <Header />
                    <main className="flex-1 overflow-y-auto">
                      {children}
                    </main>
                  </HeaderProvider>
                </ChatProvider>
              </ToastProvider>
            </SettingsProvider>
          </div>
        </div>
      </body>
    </html>
  );
}
