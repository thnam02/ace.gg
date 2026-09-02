import Image from "next/image";
import Link from "next/link";
import { ArrowsLeftRightIcon, TrophyIcon } from "@phosphor-icons/react/dist/ssr";

import { StatusBadge } from "@/components/status-badge";
import { BRAND } from "@/lib/brand";
import type { HealthResponse } from "@/lib/types";

type SiteHeaderProps = {
  health: HealthResponse | null;
};

export function SiteHeader({ health }: SiteHeaderProps) {
  return (
    <header className="sticky top-0 z-20 border-b border-white/20 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-3 px-3 py-2 sm:px-4">
        <Link
          href="/"
          className="flex min-w-0 items-center transition-opacity duration-200 hover:opacity-90"
        >
          <Image
            src={BRAND.logoSrc}
            alt={BRAND.name}
            width={196}
            height={64}
            className="h-7 w-auto sm:h-8"
            priority
          />
        </Link>
        <nav aria-label="Primary" className="flex items-center gap-1 text-sm">
          <Link
            href="/rankings"
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
          >
            <TrophyIcon className="size-3.5" aria-hidden="true" />
            Rankings
          </Link>
          <Link
            href="/compare"
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
          >
            <ArrowsLeftRightIcon className="size-3.5" aria-hidden="true" />
            Compare
          </Link>
        </nav>
        <StatusBadge health={health} />
      </div>
    </header>
  );
}
