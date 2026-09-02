import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CompareDrivers } from "@/components/compare-drivers";
import { ComparePlayerCard } from "@/components/compare-player-card";
import { CompareScouting } from "@/components/compare-scouting";
import { CompareSearchResults, CompareSelector } from "@/components/compare-selector";
import { compareCardGridClass } from "@/lib/compare";
import type { PlayerCompareEntry } from "@/lib/types";

function entry(overrides: {
  id: string;
  handle: string;
  cir: number;
  rank: number | null;
  role?: string;
  tier?: string;
  kpr?: number;
  expectedKpr?: number;
  kprResidual?: number;
  dpr?: number;
  expectedDpr?: number;
  deathResidual?: number;
  sample?: string;
  clutch?: number | null;
}): PlayerCompareEntry {
  return {
    player: {
      id: overrides.id,
      vlr_player_id: 1,
      handle: overrides.handle,
      real_name: null,
      country: null,
      team: {
        id: "t",
        vlr_team_id: 1,
        name: "LEVIATÁN",
        tag: "LEV",
        region: "LA",
      },
    },
    stats: {
      matches: 10,
      maps_played: 10,
      rounds: 200,
      acs: 220,
      kd: 1.1,
      hs_percent: 25,
      adr: 140,
      win_rate: 0.5,
    },
    aggregate: {
      raw: {
        rounds: 200,
        maps_played: 10,
        kills: 1,
        deaths: 1,
        assists: 1,
        first_kills: 1,
        first_deaths: 1,
        weighted_adr: 140,
        weighted_kast: 70,
        weighted_acs: 220,
        clutch_attempts: overrides.clutch == null ? null : 4,
      },
      derived: {
        kpr: overrides.kpr ?? 0.8,
        dpr: overrides.dpr ?? 0.6,
        apr: 0.2,
        fkpr: 0.1,
        fdpr: 0.08,
        opening_frequency: 0.25,
        opening_efficiency: 0.6,
        raw_clutch_rate: overrides.clutch ?? null,
      },
      maps: [],
    },
    cir: {
      cir: overrides.cir,
      rank: overrides.rank,
      role: overrides.role ?? "Sentinel",
      tier: overrides.tier ?? "T1",
      reliability: "HIGH",
      rounds: 977,
      maps: 40,
      kpr: overrides.kpr ?? 0.82,
      expected_kpr: overrides.expectedKpr ?? 0.7,
      kpr_residual: overrides.kprResidual ?? 0.12,
      dpr: overrides.dpr ?? 0.58,
      expected_dpr: overrides.expectedDpr ?? 0.69,
      negative_dpr_residual: overrides.deathResidual ?? 0.11,
      combat_factor: 0.5,
      sample_status: overrides.sample ?? "ESTABLISHED",
      metric_version: "v0.2-real-2026",
    },
  };
}

describe("compare selector", () => {
  it("hides suggestions until the search field has a query", () => {
    const html = renderToStaticMarkup(
      <CompareSelector
        selectedIds={[]}
        selectedChips={[]}
        onAdd={() => null}
        onRemove={() => undefined}
      />,
    );
    expect(html).toContain("Search player");
    expect(html).not.toContain("Player matches");
    expect(html).not.toContain("Searching");
  });

  it("renders matches under search so a player can be chosen", () => {
    const html = renderToStaticMarkup(
      <CompareSearchResults
        id="matches"
        query="neo"
        loading={false}
        onSelect={() => undefined}
        players={[
          {
            id: "a",
            handle: "Neon",
            real_name: null,
            team: { id: "t", vlr_team_id: 1, name: "LEVIATÁN", tag: "LEV", region: null },
            role: "Sentinel",
            tier: "T1",
            cir: 99.8,
            rounds: 1487,
            sample_status: "ESTABLISHED",
            reliability: "HIGH",
          },
        ]}
      />,
    );
    expect(html).toContain("Player matches");
    expect(html).toContain("Neon");
    expect(html).toContain("LEVIATÁN");
    expect(html).toContain("99.8");
  });
});

describe("compare cards", () => {
  it("shows actual CIR, global rank, and role+tier context", () => {
    const html = renderToStaticMarkup(
      <ComparePlayerCard
        entry={entry({ id: "a", handle: "Neon", cir: 99.8, rank: 1 })}
        count={2}
        onRemove={() => undefined}
      />,
    );
    expect(html).toContain("99.8");
    expect(html).toContain("#1");
    expect(html).toContain("CIR percentile: 99.8 out of 100");
    expect(html).not.toContain("CIR percentile: 100 out of 100");
    expect(html).toContain("Compared with T1 Sentinels");
    expect(html).toContain("+0.12 kills/round vs expected");
    expect(html).toContain("0.11 fewer deaths/round than expected");
    expect(html).toContain("CIR percentile: 99.8 out of 100");
  });

  it("shows Unranked for provisional players instead of a selected-set rank", () => {
    const html = renderToStaticMarkup(
      <ComparePlayerCard
        entry={entry({
          id: "b",
          handle: "Boaster",
          cir: 48.6,
          rank: null,
          sample: "PROVISIONAL",
          role: "Controller",
        })}
        count={2}
        onRemove={() => undefined}
      />,
    );
    expect(html).toContain("48.6");
    expect(html).toContain("Unranked");
    expect(html).toContain("Compared with T1 Controllers");
  });

  it("uses 2/3/4 card grid classes", () => {
    expect(compareCardGridClass(2)).toContain("md:grid-cols-2");
    expect(compareCardGridClass(3)).toContain("lg:grid-cols-3");
    expect(compareCardGridClass(4)).toContain("xl:grid-cols-4");
  });
});

describe("CIR driver comparison", () => {
  it("compares residuals and can mark the better kill-production residual", () => {
    const html = renderToStaticMarkup(
      <CompareDrivers
        players={[
          entry({
            id: "s",
            handle: "something",
            cir: 99,
            rank: 2,
            kpr: 0.84,
            expectedKpr: 0.75,
            kprResidual: 0.09,
          }),
          entry({
            id: "n",
            handle: "Neon",
            cir: 100,
            rank: 1,
            kpr: 0.82,
            expectedKpr: 0.7,
            kprResidual: 0.12,
          }),
        ]}
      />,
    );
    expect(html).toContain("Kill production vs expectation");
    expect(html).toContain("+0.12");
    expect(html).toContain("+0.09");
    expect(html).toContain("Best of selected");
  });

  it("renders negative death-avoidance residuals", () => {
    const html = renderToStaticMarkup(
      <CompareDrivers
        players={[
          entry({ id: "a", handle: "A", cir: 40, rank: null, deathResidual: -0.06 }),
          entry({ id: "b", handle: "B", cir: 80, rank: 4, deathResidual: 0.11 }),
        ]}
      />,
    );
    expect(html).toContain("-0.06");
    expect(html).toContain("below expectation");
  });
});

describe("scouting comparison", () => {
  it("shows the disclaimer, tabs, and clutch N/A", () => {
    const combat = renderToStaticMarkup(
      <CompareScouting
        players={[
          entry({ id: "a", handle: "Neon", cir: 100, rank: 1, clutch: null }),
          entry({ id: "b", handle: "something", cir: 90, rank: 2, clutch: null }),
        ]}
      />,
    );
    expect(combat).toContain("These stats describe playstyle and do not directly affect CIR.");
    expect(combat).toContain("Combat");
    expect(combat).toContain("ACS");
    expect(combat).toContain("Best of selected");
    const opening = renderToStaticMarkup(
      <CompareScouting
        initialTab="Opening"
        players={[
          entry({ id: "a", handle: "Neon", cir: 100, rank: 1 }),
          entry({ id: "b", handle: "something", cir: 90, rank: 2 }),
        ]}
      />,
    );
    expect(opening).toContain("Opening frequency");
    expect(opening).toContain("Opening efficiency");
    const other = renderToStaticMarkup(
      <CompareScouting
        initialTab="Other"
        players={[
          entry({ id: "a", handle: "Neon", cir: 100, rank: 1, clutch: null }),
          entry({ id: "b", handle: "something", cir: 90, rank: 2, clutch: null }),
        ]}
      />,
    );
    expect(other).toContain("Clutch");
    expect(other).toContain("N/A");
  });
});
