import type { PlayerProfile } from "@valorant-scout/shared";

import { ExternalLinkIcon } from "@/components/icons";

type PlayerCardProps = {
  player: PlayerProfile;
};

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function isVlrProfileUrl(value: string): boolean {
  return value.startsWith("https://www.vlr.gg/player/");
}

export function PlayerCard({ player }: PlayerCardProps) {
  const profileUrl = isVlrProfileUrl(player.riot_id) ? player.riot_id : null;

  return (
    <article className="group panel flex flex-col p-5 transition-[border-color,box-shadow] duration-150 hover:border-accent/40 hover:shadow-[0_0_24px_-8px_var(--glow)] motion-reduce:transition-none">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-[family-name:var(--font-barlow)] text-xs font-semibold tracking-[0.18em] text-accent uppercase">
            {player.region}
          </p>
          <h3 className="mt-1 truncate font-[family-name:var(--font-barlow)] text-2xl font-semibold tracking-tight">
            {player.display_name}
          </h3>
        </div>
        <span className="shrink-0 rounded-lg border border-border bg-surface-raised px-2.5 py-1 font-[family-name:var(--font-mono)] text-xs text-muted">
          {player.rank}
        </span>
      </div>

      <p className="mt-2 truncate text-sm text-muted">{player.team ?? "Free agent"}</p>

      {profileUrl ? (
        <a
          href={profileUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="focus-ring mt-2 inline-flex max-w-full cursor-pointer items-center gap-1.5 truncate font-[family-name:var(--font-mono)] text-xs text-muted transition-colors hover:text-accent"
        >
          <span className="truncate">VLR profile</span>
          <ExternalLinkIcon className="size-3 shrink-0" />
        </a>
      ) : (
        <p className="mt-2 truncate font-[family-name:var(--font-mono)] text-xs text-muted/70">
          {player.riot_id}
        </p>
      )}

      <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-border pt-4">
        <StatCell label="ACS" value={player.stats.acs.toFixed(1)} highlight />
        <StatCell label="K/D" value={player.stats.kd.toFixed(2)} />
        <StatCell label="HS%" value={`${player.stats.hs_percent.toFixed(1)}%`} />
        <StatCell label="Win rate" value={formatPercent(player.stats.win_rate)} />
      </dl>

      <div className="mt-4 flex items-center justify-between text-xs text-muted">
        <span>{player.stats.matches} maps sampled</span>
        <span className="font-[family-name:var(--font-mono)]">ADR {player.stats.adr.toFixed(1)}</span>
      </div>
    </article>
  );
}

function StatCell({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-xl bg-black/20 px-3 py-2.5">
      <dt className="text-[11px] font-medium tracking-wide text-muted uppercase">{label}</dt>
      <dd
        className={`mt-0.5 font-[family-name:var(--font-mono)] text-lg ${highlight ? "text-accent" : "text-foreground"}`}
      >
        {value}
      </dd>
    </div>
  );
}
