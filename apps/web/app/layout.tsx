import { Fira_Code, Fira_Sans } from "next/font/google";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { SiteHeader } from "@/components/site-header";
import { fetchHealth } from "@/lib/api";
import { BRAND } from "@/lib/brand";

import "./globals.css";

const firaSans = Fira_Sans({
  variable: "--font-fira-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const firaCode = Fira_Code({
  variable: "--font-fira-code",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: {
    default: BRAND.name,
    template: `%s · ${BRAND.name}`,
  },
  description: BRAND.description,
  icons: {
    icon: BRAND.markSrc,
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  const health = await fetchHealth();

  return (
    <html
      lang="en"
      className={`${firaSans.variable} ${firaCode.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col font-sans">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-accent focus:px-3 focus:py-1 focus:text-on-accent"
        >
          Skip to content
        </a>
        <SiteHeader health={health} />
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-3 py-4 sm:px-4">
          {children}
        </main>
      </body>
    </html>
  );
}
