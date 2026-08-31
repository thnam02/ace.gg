import Link from "next/link";

import { CrosshairIcon } from "@/components/icons";
import { StatusBadge } from "@/components/status-badge";
import type { HealthResponse } from "@valorant-scout/shared";

type SiteHeaderProps = {
  health: HealthResponse | null;
  playerCount: number;
};

export function SiteHeader({ health, playerCount }: SiteHeaderProps) {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <div
            className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-accent/30 bg-accent-soft text-accent"
            aria-hidden="true"
          >
            <CrosshairIcon className="size-5" />
          </div>
          <div className="min-w-0">
            <p className="font-[family-name:var(--font-barlow)] text-xs font-semibold tracking-[0.28em] text-accent uppercase">
              Valorant Scout
            </p>
            <h1 className="truncate font-[family-name:var(--font-barlow)] text-xl font-semibold tracking-tight sm:text-2xl">
              Pro player intelligence
            </h1>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <span className="hidden text-sm text-muted sm:inline">
            {playerCount} {playerCount === 1 ? "player" : "players"} tracked
          </span>
          <StatusBadge health={health} />
        </div>
      </div>

      <nav
        className="mx-auto flex w-full max-w-6xl gap-1 border-t border-border px-4 sm:px-6"
        aria-label="Primary"
      >
        <Link
          href="/"
          className="focus-ring cursor-pointer border-b-2 border-accent px-3 py-2.5 text-sm font-medium text-foreground transition-colors"
        >
          Roster
        </Link>
        <Link
          href="/compare"
          className="focus-ring cursor-pointer px-3 py-2.5 text-sm text-muted transition-colors hover:text-foreground motion-reduce:transition-none"
        >
          Compare
        </Link>
        <span className="cursor-default px-3 py-2.5 text-sm text-muted/60">Matches</span>
      </nav>
    </header>
  );
}
