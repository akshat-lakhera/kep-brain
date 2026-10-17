import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Suspense } from "react";
import { TopBar } from "@/components/TopBar";
import { DataChip, Footer } from "@/components/Frame";
import { Shortcuts } from "@/components/Shortcuts";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });
const mono = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: { default: "KEP Brain", template: "%s - KEP Brain" },
  description:
    "KEP Brain answers why a Kubernetes enhancement is designed the way it is, who decided and on what evidence, who owns and knows it, and whether its record is current, and lists the decision records that disagree.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f8f8" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0e12" },
  ],
};

// Applies the stored theme choice (or the OS preference) before first paint.
const THEME_SCRIPT = `(function(){try{var c=localStorage.getItem("kep.theme");var d=c==="dark"||((c===null||c==="system")&&window.matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.setAttribute("data-theme",d?"dark":"light");}catch(e){}})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning className={`${inter.variable} ${mono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-screen flex-col antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-sm focus:bg-surface focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <TopBar
          dataChip={
            <Suspense fallback={null}>
              <DataChip />
            </Suspense>
          }
        />
        <main id="main" className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 md:px-6">
          {children}
        </main>
        <Suspense fallback={<footer className="border-t border-border bg-surface px-4 py-4 md:px-6" />}>
          <Footer />
        </Suspense>
        <Shortcuts />
      </body>
    </html>
  );
}
