import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { CirExplainer } from "@/components/home/cir-explainer";
import { HomePageView } from "@/components/home/home-page";
import { HomeSearchResults } from "@/components/home/player-search";
import { TopPlayerCard } from "@/components/home/top-player-card";
import { SiteFooter } from "@/components/site-footer";
import { BRAND } from "@/lib/brand";
import {
  HOME_BEYOND_KD,
  HOME_HEADLINE_EMPHASIS,
  HOME_HEADLINE_LEAD,
  HOME_METADATA_DESCRIPTION,
  HOME_METADATA_TITLE,
  HOME_RIOT_DISCLAIMER,
} from "@/lib/home";
import type { CirPlayerDetail, CirRankingPlayer, PlayerOption } from "@/lib/types";

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

function rankingPlayer(
  index: number,
  overrides: Partial<CirRankingPlayer> = {},
): CirRankingPlayer {
  return {
    rank: index,
    player_id: `player-${index}`,
    handle: `Player${index}`,
    team: {
      id: "team-1",
      vlr_team_id: 1,
      name: "LEVIATÁN",
      tag: "LEV",
      region: "LA",
    },
    role: "Sentinel",
    tier: "T1",
    region: "Americas",
    primary_agent: null,
    cir: 90,
    reliability: "HIGH",
    rounds: 400,
    maps: 20,
    kpr: 0.8,
    dpr: 0.6,
    sample_status: "ESTABLISHED",
    metric_version: "v0.2-real-2026",
    ...overrides,
  };
}

function option(overrides: Partial<PlayerOption> = {}): PlayerOption {
  return {
    id: "player-1",
    handle: "Neon",
    real_name: null,
    team: {
      id: "team-1",
      vlr_team_id: 1,
      name: "LEVIATÁN",
      tag: "LEV",
      region: "LA",
    },
    role: "Sentinel",
    tier: "T1",
    cir: 99.8,
    rounds: 1487,
    sample_status: "ESTABLISHED",
    reliability: "HIGH",
    ...overrides,
  };
}

describe("HomePageView", () => {
  const leader = rankingPlayer(1, {
    handle: "Aspas",
    cir: 99.8,
    rounds: 1487,
  });
  const leaderCir: CirPlayerDetail = {
    player_id: leader.player_id,
    handle: leader.handle,
    team: leader.team,
    role: leader.role,
    cir: 99.8,
    raw_cir: 99.8,
    reliability: "HIGH",
    reliability_pct: 0.9,
    sample_status: "ESTABLISHED",
    rounds: 1487,
    maps: 40,
    combat_factor: 1.2,
    kpr: 0.79,
    dpr: 0.59,
    expected_kpr: 0.7,
    expected_dpr: 0.69,
    kpr_residual: 0.12,
    negative_dpr_residual: 0.11,
    metric_version: "v0.2-real-2026",
    reference_period_start: null,
    reference_period_end: null,
    interpretation: null,
    rank: 1,
    established_count: 408,
  };

  it("renders ACE.gg branding, headline, and primary CTAs", () => {
    const html = renderToStaticMarkup(
      <HomePageView
        topPlayers={[leader]}
        establishedCount={408}
        rankingsError={false}
        metadata={{
          name: "CIR",
          version: "v0.2-real-2026",
          status: "PRODUCTION",
          description: "CIR",
          tooltip: "CIR",
          interpretation: "CIR",
          features: [],
          context: "role + competitive tier",
          scale: "0–100",
          established_sample: 250,
          last_data_sync_at: "2026-09-03T03:00:00+00:00",
          season: 2026,
          circuit: "VCT",
        }}
        leader={leader}
        leaderCir={leaderCir}
      />,
    );

    expect(html).toContain(BRAND.name);
    expect(html).toContain(HOME_HEADLINE_LEAD);
    expect(html).toContain(HOME_HEADLINE_EMPHASIS);
    expect(html).toContain("<h1");
    expect(html).toContain('href="/rankings"');
    expect(html).toContain("Explore rankings");
    expect(html).toContain('href="/compare"');
    expect(html).toContain("Compare players");
    expect(html).toContain("Search player or team...");
    expect(html).toContain("Aspas");
    expect(html).not.toContain("Neon");
    expect(html).toContain("99.8");
    expect(html).not.toContain(">100<");
    expect(html).not.toContain("99.8%");
    expect(html).toContain("408");
    expect(html).toContain("Established players");
    expect(html).toContain("2026");
    expect(html).toContain("Updated Sep 3, 2026");
    expect(html).toContain("View all rankings");
    expect(html).toContain("How CIR works");
    expect(html).toContain("Contextual Impact Rating");
    expect(html).toContain("kill production and death avoidance against expectations");
    expect(html).toContain(HOME_BEYOND_KD);
    expect(html).toContain(">Example<");
    expect(html).toContain("View rankings");
    expect(html).toContain("Find a player");
    expect(html).toContain('href="#player-search"');
    expect(html).not.toContain("Include provisional");
    expect(html).not.toContain("tau=");
    expect(html).not.toContain("lambda");
    expect(html).toContain("lg:grid-cols-2");
    expect(html).toContain("sm:grid-cols-2 lg:grid-cols-3");
    expect(html).toContain("grid-cols-2");
    expect(html).toContain("lg:grid-cols-4");
    expect(html).toContain("md:grid-cols-3");
    expect(html).toContain("md:grid-cols-2 lg:grid-cols-3");
  });

  it("renders top-player profile links from ranking data", () => {
    const html = renderToStaticMarkup(
      <HomePageView
        topPlayers={[leader, rankingPlayer(2, { handle: "TenZ", cir: 96.8 })]}
        establishedCount={408}
        rankingsError={false}
        metadata={null}
        leader={leader}
        leaderCir={leaderCir}
      />,
    );
    expect(html).toContain('href="/players/player-1"');
    expect(html).toContain('href="/players/player-2"');
    expect(html).toContain("TenZ");
    expect(html).toContain("Top CIR Players");
  });

  it("caps the top-player grid at six cards", () => {
    const html = renderToStaticMarkup(
      <HomePageView
        topPlayers={Array.from({ length: 8 }, (_, index) => rankingPlayer(index + 1))}
        establishedCount={8}
        rankingsError={false}
        metadata={null}
        leader={rankingPlayer(1)}
        leaderCir={null}
      />,
    );
    expect(html).toContain("Player6");
    expect(html).not.toContain("Player7");
  });

  it("shows an empty ranking state without placeholder cards", () => {
    const html = renderToStaticMarkup(
      <HomePageView
        topPlayers={[]}
        establishedCount={0}
        rankingsError={false}
        metadata={null}
        leader={null}
        leaderCir={null}
      />,
    );
    expect(html).toContain("No established player rankings are available yet.");
    expect(html).not.toContain("View profile →");
    expect(html).toContain(HOME_HEADLINE_LEAD);
    expect(html).toContain("Explore rankings");
  });

  it("falls back when the ranking API fails without breaking the hero", () => {
    const html = renderToStaticMarkup(
      <HomePageView
        topPlayers={[]}
        establishedCount={null}
        rankingsError={true}
        metadata={null}
        leader={null}
        leaderCir={null}
      />,
    );
    expect(html).toContain("Unable to load current rankings.");
    expect(html).toContain("Open rankings");
    expect(html).toContain(HOME_HEADLINE_LEAD);
    expect(html).toContain("Contextual Impact Rating");
    expect(html).not.toContain("Established players");
  });
});

describe("TopPlayerCard", () => {
  it("keeps CIR as the strongest value and avoids a prominent missing-team dash", () => {
    const html = renderToStaticMarkup(
      <TopPlayerCard
        player={rankingPlayer(1, {
          handle: "Aspas",
          cir: 99.8,
          rounds: 1487,
          team: null,
        })}
      />,
    );
    expect(html).toContain("99.8");
    expect(html).not.toContain("99.8%");
    expect(html).not.toContain(">100<");
    expect(html).toContain("Unattached · Sentinel");
    expect(html).not.toContain("— ·");
    expect(html).toContain("HIGH · 1,487 rounds");
    expect(html).toContain('href="/players/player-1"');
    expect(html).toContain("View profile →");
    expect(html).toContain("text-3xl");
  });
});

describe("CirExplainer", () => {
  it("explains CIR in three steps and labels the numeric example", () => {
    const html = renderToStaticMarkup(<CirExplainer />);
    expect(html).toContain("How CIR works");
    expect(html).toContain("Compare to expectation");
    expect(html).toContain("Measure combat performance");
    expect(html).toContain("Convert to percentile");
    expect(html).toContain("Role + Tier");
    expect(html).toContain("Example");
    expect(html).toContain("T1 Controller");
    expect(html).toContain("Beyond K/D and ACS");
    expect(html).not.toContain("tau");
    expect(html).not.toContain("PCA");
  });
});

describe("HomeSearchResults", () => {
  it("shows handle, team, role, CIR, and sample status", () => {
    const html = renderToStaticMarkup(
      <HomeSearchResults id="results" players={[option()]} loading={false} error={null} />,
    );
    expect(html).toContain("Neon");
    expect(html).toContain("LEVIATÁN · Sentinel");
    expect(html).toContain("CIR 99.8");
    expect(html).toContain("Established");
    expect(html).toContain('href="/players/player-1"');
  });

  it("does not fake a zero CIR and clears to an empty state", () => {
    const found = renderToStaticMarkup(
      <HomeSearchResults
        id="results"
        players={[option({ cir: null, sample_status: "PROVISIONAL" })]}
        loading={false}
        error={null}
      />,
    );
    expect(found).toContain("CIR unavailable");
    expect(found).not.toContain("CIR 0");
    expect(found).toContain("Provisional");

    const empty = renderToStaticMarkup(
      <HomeSearchResults id="results" players={[]} loading={false} error={null} />,
    );
    expect(empty).toContain("No players found.");
    expect(empty).not.toContain("Neon");
  });
});

describe("SiteFooter", () => {
  it("includes ACE.gg navigation and a subtle Riot disclaimer", () => {
    const html = renderToStaticMarkup(<SiteFooter />);
    expect(html).toContain(BRAND.name);
    expect(html).toContain('href="/rankings"');
    expect(html).toContain('href="/compare"');
    expect(html).toContain(HOME_RIOT_DISCLAIMER);
  });
});

describe("homepage metadata copy", () => {
  it("uses ACE.gg product metadata", () => {
    expect(HOME_METADATA_TITLE).toBe("ACE.gg — VALORANT Player Analytics");
    expect(HOME_METADATA_DESCRIPTION).toContain("CIR");
    expect(BRAND.description).toBe(HOME_METADATA_DESCRIPTION);
  });
});
