import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { PlayerDossier } from "@/components/player-dossier";
import { SCOUTING_DISCLAIMER } from "@/lib/player-cir-copy";
import type { CirPlayerDetail, PlayerDetailResponse, PlayerIdentity } from "@/lib/types";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    className?: string;
    "aria-label"?: string;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function fixture(overrides?: {
  cir?: Partial<CirPlayerDetail>;
  clutch?: number | null;
  clutchAttempts?: number | null;
  player?: Partial<PlayerIdentity>;
  stats?: Partial<PlayerDetailResponse["stats"]>;
  derived?: Partial<PlayerDetailResponse["aggregate"]["derived"]>;
}): { detail: PlayerDetailResponse; cir: CirPlayerDetail } {
  const detail: PlayerDetailResponse = {
    player: {
      id: "player-neon",
      vlr_player_id: 1,
      handle: "Neon",
      real_name: null,
      country: "CL",
      team: {
        id: "team-1",
        vlr_team_id: 1,
        name: "LEVIATÁN",
        tag: "LEV",
        region: "LA",
      },
      ...overrides?.player,
    },
    stats: {
      matches: 40,
      maps_played: 40,
      rounds: 977,
      acs: 240,
      kd: 1.2,
      hs_percent: 28,
      adr: 150,
      win_rate: 0.55,
      ...overrides?.stats,
    },
    aggregate: {
      raw: {
        rounds: 977,
        maps_played: 40,
        kills: 800,
        deaths: 600,
        assists: 200,
        first_kills: 120,
        first_deaths: 80,
        weighted_adr: 150,
        weighted_kast: 72,
        weighted_acs: 240,
        clutch_wins: overrides?.clutchAttempts ? 0 : null,
        clutch_attempts: overrides?.clutchAttempts ?? null,
      },
      derived: {
        kpr: 0.82,
        dpr: 0.58,
        apr: 0.2,
        fkpr: 0.12,
        fdpr: 0.08,
        opening_frequency: 0.25,
        opening_efficiency: 0.6,
        raw_clutch_rate: overrides?.clutch === undefined ? null : overrides.clutch,
        ...overrides?.derived,
      },
      maps: [],
    },
  };

  const cir: CirPlayerDetail = {
    player_id: "player-neon",
    handle: "Neon",
    team: detail.player.team,
    role: "Sentinel",
    tier: "T1",
    rank: 1,
    established_count: 343,
    cir: 100,
    raw_cir: 1,
    reliability: "HIGH",
    reliability_pct: 100,
    sample_status: "ESTABLISHED",
    rounds: 977,
    maps: 40,
    combat_factor: 1,
    kpr: 0.82,
    dpr: 0.58,
    expected_kpr: 0.7,
    expected_dpr: 0.69,
    kpr_residual: 0.12,
    negative_dpr_residual: 0.11,
    metric_version: "v0.2-real-2026",
    reference_period_start: "2026-01-01",
    reference_period_end: "2026-12-31",
    interpretation: null,
    ...overrides?.cir,
  };

  return { detail, cir };
}

describe("PlayerDossier", () => {
  it("renders CIR hero, rank, and context without 100+ percentile wording", () => {
    const { detail, cir } = fixture();
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain("CIR");
    expect(html).toContain(">100<");
    expect(html).toContain("#1 / 343");
    expect(html).toContain("Established ranking");
    expect(html).toContain("Top percentile of the 2026 reference population");
    expect(html).not.toContain("100+");
    expect(html).not.toContain("percentile interpretation");
    expect(html).toContain("Compared with T1 Sentinels");
    expect(html).toContain("CIR v0.2 · 2026 reference");
    expect(html).toContain("HIGH");
    expect(html).toContain("977");
    expect(html).toContain("ESTABLISHED");
    expect(html).toContain("Compare player");
    expect(html).toContain("/compare?ids=player-neon");
    expect(html).not.toContain("PCA");
    expect(html).not.toContain("z-score");
  });

  it("keeps CIR 99.8 instead of rounding to 100", () => {
    const { detail, cir } = fixture({ cir: { cir: 99.8 } });
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain(">99.8<");
    expect(html).not.toMatch(/aria-label="CIR 100"/);
    expect(html).toContain("Around the 99th percentile of the 2026 reference population");
    expect(html).toContain("CIR percentile: 99.8 out of 100");
  });

  it("renders the crazyguy scouting example without recomputing CIR", () => {
    const { detail, cir } = fixture({
      player: {
        id: "player-crazyguy",
        handle: "crazyguy",
        team: {
          id: "team-rrq",
          vlr_team_id: 2,
          name: "Rex Regum Qeon",
          tag: "RRQ",
          region: "PAC",
        },
      },
      stats: {
        acs: 182.2,
        adr: 120,
        kd: 0.9,
        hs_percent: 25.5,
      },
      derived: {
        opening_frequency: 0.17,
        opening_efficiency: 0.38,
        fkpr: 0.07,
        fdpr: 0.11,
      },
      cir: {
        player_id: "player-crazyguy",
        handle: "crazyguy",
        role: "Controller",
        tier: "T1",
        rank: 319,
        established_count: 408,
        cir: 30.3,
        reliability: "HIGH",
        sample_status: "ESTABLISHED",
        rounds: 1090,
        kpr: 0.61,
        dpr: 0.7,
        expected_kpr: 0.65,
        expected_dpr: 0.67,
        kpr_residual: -0.04,
        negative_dpr_residual: -0.03,
      },
    });
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain("crazyguy");
    expect(html).toContain("Rex Regum Qeon");
    expect(html).toContain("Controller");
    expect(html).toContain("Main role Controller");
    expect(html).toContain(">30.3<");
    expect(html).toContain("#319 / 408");
    expect(html).toContain("HIGH");
    expect(html).toContain("1,090");
    expect(html).toContain("ESTABLISHED");
    expect(html).toContain("Compared with T1 Controllers");
    expect(html).toContain("0.61 KPR");
    expect(html).toContain("Expected 0.65");
    expect(html).toContain("-0.04 vs expected");
    expect(html).toContain("Below expected");
    expect(html).toContain("0.70 DPR");
    expect(html).toContain("Expected 0.67");
    expect(html).toContain("0.03 more deaths/round than expected");
    expect(html).toContain("182.2");
    expect(html).toContain("120.0");
    expect(html).toContain("0.90");
    expect(html).toContain("25.5%");
    expect(html).toContain(">17%<");
    expect(html).toContain(">38%<");
    expect(html).toContain("0.07");
    expect(html).toContain("0.11");
    expect(html).toContain("role=\"progressbar\"");
    expect(html).toContain("aria-valuemin=\"0\"");
    expect(html).toContain("aria-valuemax=\"100\"");
    expect(html).toContain("aria-valuenow=\"30.3\"");
  });

  it("highlights the main role when a player also plays others", () => {
    const { detail, cir } = fixture({
      cir: {
        role: "Controller",
        roles: [
          { role: "Controller", rounds: 600, share: 0.6, is_main: true },
          { role: "Sentinel", rounds: 400, share: 0.4, is_main: false },
        ],
      },
    });
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain("Main role Controller, also Sentinel");
    expect(html).toContain("font-medium text-foreground");
    expect(html).toContain("Compared with T1 Controllers");
  });

  it("shows expected KPR/DPR and above/below wording with text, not color only", () => {
    const { detail, cir } = fixture();
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain("Why this score");
    expect(html).toContain("0.82 KPR");
    expect(html).toContain("Expected 0.70");
    expect(html).toContain("+0.12 vs expected");
    expect(html).toContain("Above expected");
    expect(html).toContain("0.58 DPR");
    expect(html).toContain("Expected 0.69");
    expect(html).toContain("0.11 fewer deaths/round than expected");
    expect(html).toContain(SCOUTING_DISCLAIMER);
    expect(html).toContain("Additional scouting stats");
    expect(html).toContain("CIR percentile: 100 out of 100");
  });

  it("renders below-expectation wording for weaker combat", () => {
    const { detail, cir } = fixture({
      cir: { kpr_residual: -0.08, negative_dpr_residual: -0.09 },
    });
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain("-0.08 vs expected");
    expect(html).toContain("Below expected");
    expect(html).toContain("0.09 more deaths/round than expected");
  });

  it("renders missing clutch and missing scouting stats as N/A", () => {
    const { detail, cir } = fixture({
      clutch: null,
      clutchAttempts: null,
      stats: { acs: null, adr: null, kd: null, hs_percent: null, win_rate: null },
      derived: { opening_frequency: null, opening_efficiency: null, apr: null },
    });
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain("Clutch");
    expect(html).toMatch(/Clutch[\s\S]*N\/A/);
    expect(html).not.toMatch(/Clutch[\s\S]*>0</);
    expect(html).toMatch(/ACS[\s\S]*N\/A/);
    expect(html).toContain(">N/A<");
  });

  it("does not invent a team or rank", () => {
    const { detail, cir } = fixture({
      player: { team: null },
      cir: { rank: null, sample_status: "PROVISIONAL", reliability: "MEDIUM", rounds: 143, cir: 85.1 },
    });
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain("Unattached");
    expect(html).toContain("Sentinel");
    expect(html).toContain("Main role Sentinel");
    expect(html).not.toContain("— ·");
    expect(html).toContain("Not ranked");
    expect(html).toContain("Not in established ranking");
    expect(html).toContain(">85.1<");
    expect(html).toContain("MEDIUM");
    expect(html).toContain("PROVISIONAL");
    expect(html).toContain("143");
  });

  it("shows CIR unavailable when the score is missing", () => {
    const { detail, cir } = fixture({ cir: { cir: null } });
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain("CIR unavailable");
  });

  it("uses mobile-safe stacked layout classes", () => {
    const { detail, cir } = fixture();
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    expect(html).toContain("md:grid-cols-2");
    expect(html).toContain("md:grid-cols-4");
    expect(html).toContain("min-w-0");
    expect(html).toContain("max-w-[1200px]");
    expect(html).not.toContain("min-w-[720px]");
  });

  it("keeps scouting stats after the CIR disclaimer", () => {
    const { detail, cir } = fixture();
    const html = renderToStaticMarkup(<PlayerDossier detail={detail} cir={cir} />);
    const disclaimerAt = html.indexOf(SCOUTING_DISCLAIMER);
    expect(disclaimerAt).toBeGreaterThan(html.indexOf("Why this score"));
    expect(html.indexOf("ACS")).toBeGreaterThan(disclaimerAt);
    expect(html.indexOf("Opening frequency")).toBeGreaterThan(disclaimerAt);
    expect(html).toContain("First kills per round");
    expect(html).toContain("25% of rounds involved in the opening duel");
    expect(html).toContain(">25%<");
    expect(html).toContain(">60%<");
  });
});
