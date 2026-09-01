import {
  formatAcs,
  formatAdr,
  formatHs,
  formatKd,
  formatWinRate,
  teamLabel,
} from "@/lib/format";
import type { PlayerProfile } from "@/lib/types";

type MetricKey = "acs" | "kd" | "hs_percent" | "adr" | "win_rate" | "matches";

type MetricRow = {
  key: MetricKey;
  label: string;
  value: (player: PlayerProfile) => number;
  format: (value: number) => string;
};

const METRICS: MetricRow[] = [
  { key: "acs", label: "ACS", value: (player) => player.stats.acs, format: formatAcs },
  { key: "kd", label: "K/D", value: (player) => player.stats.kd, format: formatKd },
  { key: "hs_percent", label: "HS%", value: (player) => player.stats.hs_percent, format: formatHs },
  { key: "adr", label: "ADR", value: (player) => player.stats.adr, format: formatAdr },
  {
    key: "win_rate",
    label: "Win rate",
    value: (player) => player.stats.win_rate,
    format: formatWinRate,
  },
  {
    key: "matches",
    label: "Matches",
    value: (player) => player.stats.matches,
    format: (value) => String(value),
  },
];

const BAR_STYLES = [
  { bar: "bg-accent", pattern: "" },
  { bar: "bg-secondary", pattern: "bar-stripe" },
  { bar: "bg-muted-foreground", pattern: "bar-dots" },
];

type CompareViewProps = {
  players: PlayerProfile[];
  notes: string;
};

export function CompareView({ players, notes }: CompareViewProps) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{notes}</p>
      <div className="overflow-x-auto rounded-xl">
        <table className="glass-panel min-w-[640px] w-full border-collapse text-left text-sm">
          <caption className="sr-only">Side-by-side player comparison</caption>
          <thead className="bg-muted/60 text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                Metric
              </th>
              {players.map((player) => (
                <th key={player.id} scope="col" className="px-3 py-2 font-medium">
                  {player.display_name}
                  <span className="mt-0.5 block font-sans text-[11px] normal-case text-muted-foreground">
                    {teamLabel(player.team)} · {player.region}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {METRICS.map((metric) => {
              const values = players.map((player) => metric.value(player));
              const best = Math.max(...values);
              return (
                <tr key={metric.key} className="border-t border-white/10">
                  <th scope="row" className="px-3 py-1.5 text-left font-medium text-muted-foreground">
                    {metric.label}
                  </th>
                  {players.map((player) => {
                    const value = metric.value(player);
                    const isBest = value === best && players.length > 1;
                    return (
                      <td
                        key={player.id}
                        className={`px-3 py-1.5 font-mono tabular-nums ${isBest ? "text-accent" : "text-foreground"}`}
                      >
                        {metric.format(value)}
                        {isBest ? <span className="sr-only"> (highest)</span> : null}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <section className="glass-panel rounded-xl p-3" aria-label="Grouped metric bars">
        <h2 className="mb-3 text-sm font-medium">Metric bars</h2>
        <ul className="space-y-3">
          {METRICS.filter((metric) => metric.key !== "matches").map((metric) => {
            const values = players.map((player) => metric.value(player));
            const max = Math.max(...values, Number.EPSILON);
            return (
              <li key={metric.key}>
                <p className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                  {metric.label}
                </p>
                <div className="space-y-1">
                  {players.map((player, index) => {
                    const value = metric.value(player);
                    const width = Math.max(8, (value / max) * 100);
                    const style = BAR_STYLES[index % BAR_STYLES.length];
                    return (
                      <div key={player.id} className="grid grid-cols-[7rem_1fr_auto] items-center gap-2">
                        <span className="truncate text-xs text-foreground">{player.display_name}</span>
                        <div className="h-4 overflow-hidden rounded bg-muted">
                          <div
                            className={`h-full ${style.bar} ${style.pattern} transition-[width] duration-200`}
                            style={{ width: `${width}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs tabular-nums text-muted-foreground">
                          {metric.format(value)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
