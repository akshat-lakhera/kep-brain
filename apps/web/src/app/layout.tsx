import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { connection } from "next/server";
import { Suspense } from "react";
import { TopBar } from "@/components/TopBar";
import { Footer } from "@/components/Frame";
import { Shortcuts } from "@/components/Shortcuts";
import { ToastProvider } from "@/components/Toast";
import { SITE_DESCRIPTION, SITE_NAME, siteBase } from "@/lib/site";
import "./globals.css";

// One variable sans for display and body, one variable mono for identifiers; both served from this site.
const sans = Geist({ variable: "--font-geist", subsets: ["latin"], display: "swap" });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"], display: "swap" });

export async function generateMetadata(): Promise<Metadata> {
  // The base URL is the deployment's, read when a page is served rather than baked in at build time.
  await connection();
  return {
    metadataBase: new URL(siteBase()),
    title: { default: SITE_NAME, template: `%s - ${SITE_NAME}` },
    description: SITE_DESCRIPTION,
    // No title or description here: each page's own title and description fill og:title and og:description.
    openGraph: { type: "website", siteName: SITE_NAME, locale: "en_US" },
    twitter: { card: "summary_large_image" },
  };
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8f9fb" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0d14" },
  ],
};

// Applies the stored theme choice (or the OS preference) before first paint.
const THEME_SCRIPT = `(function(){try{var c=localStorage.getItem("kep.theme");var d=c==="dark"||((c===null||c==="system")&&window.matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.setAttribute("data-theme",d?"dark":"light");}catch(e){}})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning className={`${sans.variable} ${mono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-screen flex-col antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-sm focus:border focus:border-border-strong focus:bg-surface focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <ToastProvider>
          <TopBar />
          <main id="main" className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 md:px-6">
            {children}
          </main>
          <Suspense fallback={<footer className="border-t border-border bg-surface px-4 py-4 md:px-6" />}>
            <Footer />
          </Suspense>
          <Shortcuts />
        </ToastProvider>
      </body>
    </html>
  );
}
