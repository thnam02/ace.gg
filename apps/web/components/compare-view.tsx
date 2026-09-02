import {
  formatAcs,
  formatAdr,
  formatCir,
  formatRate,
  formatRounds,
  formatSignedRate,
  teamLabel,
} from "@/lib/format";
import type { PlayerCompareEntry } from "@/lib/types";

type CompareViewProps = {
  players: PlayerCompareEntry[];
  notes: string;
};

function cell(
  values: Array<number | null | undefined>,
  value: number | null | undefined,
  higherIsBetter: boolean,
): string {
  const numeric = values.filter((item): item is number => item != null);
  if (value == null || numeric.length < 2) {
    return "text-foreground";
  }
  const best = higherIsBetter ? Math.max(...numeric) : Math.min(...numeric);
  return value === best ? "text-accent" : "text-foreground";
}

export function CompareView({ players, notes }: CompareViewProps) {
  const cirRows = [
    {
      label: "CIR",
      values: players.map((entry) => entry.cir?.cir ?? null),
      format: formatCir,
      better: true,
    },
    {
      label: "Reliability",
      values: players.map((entry) => entry.cir?.reliability ?? "N/A"),
      format: (value: string | number | null) => String(value ?? "N/A"),
      better: null,
    },
    {
      label: "Rounds",
      values: players.map((entry) => entry.cir?.rounds ?? entry.stats.rounds),
      format: (value: number | null) => formatRounds(value ?? 0),
      better: true,
    },
    {
      label: "KPR",
      values: players.map((entry) => entry.cir?.kpr ?? entry.aggregate.derived.kpr),
      format: formatRate,
      better: true,
    },
    {
      label: "Expected KPR",
      values: players.map((entry) => entry.cir?.expected_kpr ?? null),
      format: formatRate,
      better: null,
    },
    {
      label: "KPR residual",
      values: players.map((entry) => entry.cir?.kpr_residual ?? null),
      format: formatSignedRate,
      better: true,
    },
    {
      label: "DPR",
      values: players.map((entry) => entry.cir?.dpr ?? entry.aggregate.derived.dpr),
      format: formatRate,
      better: false,
    },
    {
      label: "Expected DPR",
      values: players.map((entry) => entry.cir?.expected_dpr ?? null),
      format: formatRate,
      better: null,
    },
    {
      label: "Death-avoidance residual",
      values: players.map((entry) => entry.cir?.negative_dpr_residual ?? null),
      format: formatSignedRate,
      better: true,
    },
  ];

  const scoutingRows = [
    {
      label: "ACS",
      values: players.map((entry) => entry.stats.acs),
      format: formatAcs,
      better: true,
    },
    {
      label: "ADR",
      values: players.map((entry) => entry.stats.adr),
      format: formatAdr,
      better: true,
    },
    {
      label: "KAST",
      values: players.map((entry) => entry.aggregate.raw.weighted_kast),
      format: (value: number | null) => (value == null ? "N/A" : `${value.toFixed(1)}%`),
      better: true,
    },
    {
      label: "Opening frequency",
      values: players.map((entry) => entry.aggregate.derived.opening_frequency),
      format: formatRate,
      better: null,
    },
    {
      label: "Opening efficiency",
      values: players.map((entry) => entry.aggregate.derived.opening_efficiency),
      format: formatRate,
      better: true,
    },
  ];

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{notes}</p>
      <CompareTable title="CIR inputs" players={players} rows={cirRows} />
      <CompareTable title="Additional scouting stats" players={players} rows={scoutingRows} />
      <p className="text-xs text-muted-foreground">
        ACS, ADR, KAST, and opening stats are descriptive. They are not CIR inputs.
      </p>
    </div>
  );
}

type CompareRow = {
  label: string;
  values: Array<number | string | null | undefined>;
  format: (value: never) => string;
  better: boolean | null;
};

function CompareTable({
  title,
  players,
  rows,
}: {
  title: string;
  players: PlayerCompareEntry[];
  rows: CompareRow[];
}) {
  return (
    <div className="overflow-x-auto rounded-xl">
      <table className="glass-panel min-w-[640px] w-full border-collapse text-left text-sm">
        <caption className="sr-only">{title}</caption>
        <thead className="bg-muted/60 text-[11px] uppercase tracking-wide text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              {title}
            </th>
            {players.map((entry) => (
              <th key={entry.player.id} scope="col" className="px-3 py-2 font-medium">
                {entry.player.handle}
                <span className="mt-0.5 block font-sans text-[11px] normal-case text-muted-foreground">
                  {teamLabel(entry.player.team?.name ?? null)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-t border-white/10">
              <th scope="row" className="px-3 py-1.5 text-left font-medium text-muted-foreground">
                {row.label}
              </th>
              {row.values.map((value, index) => {
                const numericValues = row.values.filter(
                  (item): item is number => typeof item === "number",
                );
                const className =
                  typeof value === "number" && row.better != null
                    ? cell(numericValues, value, row.better)
                    : "text-foreground";
                return (
                  <td
                    key={players[index]?.player.id ?? index}
                    className={`px-3 py-1.5 font-mono tabular-nums ${className}`}
                  >
                    {row.format(value as never)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
