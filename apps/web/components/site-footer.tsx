import Link from "next/link";

import { BRAND } from "@/lib/brand";
import { HOME_FOOTER_BLURB, HOME_RIOT_DISCLAIMER } from "@/lib/home";

type SiteFooterProps = {
  freshness?: string;
};

export function SiteFooter({ freshness }: SiteFooterProps) {
  return (
    <footer className="mt-auto border-t border-white/10">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-4 px-3 py-6 sm:px-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-sm">
            <p className="font-sans text-sm font-semibold tracking-tight">{BRAND.name}</p>
            <p className="mt-1 text-sm text-muted-foreground">{HOME_FOOTER_BLURB}</p>
            {freshness ? (
              <p className="mt-2 text-xs text-muted-foreground">{freshness}.</p>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">Data updated daily.</p>
            )}
          </div>
          <nav aria-label="Footer" className="flex gap-4 text-sm">
            <Link
              href="/rankings"
              className="text-muted-foreground transition-colors duration-200 hover:text-foreground"
            >
              Rankings
            </Link>
            <Link
              href="/compare"
              className="text-muted-foreground transition-colors duration-200 hover:text-foreground"
            >
              Compare
            </Link>
          </nav>
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">{HOME_RIOT_DISCLAIMER}</p>
      </div>
    </footer>
  );
}
