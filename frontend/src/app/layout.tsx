import type { Metadata } from "next";
import "./globals.css";
import { LobeProvider } from "@/components/providers/LobeProvider";
import { APPLayout } from "./APPLayout";

export const metadata: Metadata = {
  title: "OtakuNeko Dashboard",
  description: "AI-powered anime dashboard",
  icons: {
    icon: "/Icon.png",
  },
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // 关键：html 和 body 必须设为 h-full (height: 100%)
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className="antialiased h-full m-0 p-0 overflow-hidden">
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
        <LobeProvider>
          <APPLayout>
            {children}
          </APPLayout>
        </LobeProvider>
      </body>
    </html>
  );
}
