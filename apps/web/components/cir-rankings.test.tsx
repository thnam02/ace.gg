import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { CirRankings } from "@/components/cir-rankings";
import type { CirRankingPlayer } from "@/lib/types";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    className?: string;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@phosphor-icons/react", async () => {
  const actual = await vi.importActual<typeof import("@phosphor-icons/react")>(
    "@phosphor-icons/react",
  );
  return {
    ...actual,
    XIcon: (props: { className?: string; "aria-hidden"?: boolean | string }) => (
      <span data-testid="x-icon" {...props} />
    ),
  };
});

function player(index: number): CirRankingPlayer {
  return {
    rank: index,
    player_id: `player-${index}`,
    handle: `Player${index}`,
    team: {
      id: "team-1",
      vlr_team_id: 1,
      name: "Sentinels",
      tag: "SEN",
      region: "NA",
    },
    role: "duelist",
    tier: "T1",
    region: "Americas",
    primary_agent: null,
    cir: 90,
    reliability: "high",
    rounds: 400,
    maps: 20,
    kpr: 0.8,
    dpr: 0.6,
    sample_status: "ESTABLISHED",
    metric_version: "v0.2-real-2026",
  };
}

describe("CirRankings pagination", () => {
  it("shows a page bar instead of the full list", () => {
    const html = renderToStaticMarkup(
      <CirRankings
        players={Array.from({ length: 51 }, (_, index) => player(index + 1))}
        total={51}
        includeProvisional={false}
        tooltip="CIR"
      />,
    );
    expect(html).toContain("Showing 1–50 of 51");
    expect(html).toContain("page 1 of 2");
    expect(html).toContain('aria-label="Page 2"');
    expect(html).toContain("Player50");
    expect(html).not.toContain("Player51");
  });

  it("renders the filter and sort bar", () => {
    const html = renderToStaticMarkup(
      <CirRankings
        players={[player(1)]}
        includeProvisional={false}
        tooltip="CIR"
      />,
    );
    expect(html).toContain('id="ranking-search"');
    expect(html).toContain('type="search"');
    expect(html).toContain(">Tier<");
    expect(html).toContain(">Region<");
    expect(html).toContain(">Event<");
    expect(html).toContain(">Role<");
    expect(html).toContain(">Sort by<");
    expect(html).toContain(">Order<");
    expect(html).toContain(">Minimum rounds<");
    expect(html).toContain("Include provisional");
    expect(html).toContain(">Apply<");
    expect(html).toContain(">Reset<");
    expect(html).toContain("Sentinels");
  });

  it("renders event-scoped title chips and player event links", () => {
    const eventId = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";
    const html = renderToStaticMarkup(
      <CirRankings
        players={[player(1)]}
        includeProvisional
        tooltip="Event CIR"
        title="Event CIR Rankings · Pacific Stage 2"
        eventScoped
        eventName="Pacific Stage 2"
        initialFilters={{
          query: "",
          tier: "T1",
          region: "Pacific",
          eventId,
          role: null,
          sort: "cir",
          order: "desc",
          minRounds: null,
        }}
        events={[
          {
            id: eventId,
            vlr_event_id: 1,
            name: "Pacific Stage 2",
            region: "Pacific",
            canonical_region: "Pacific",
            tier: "T1",
            circuit: null,
            stage: null,
            status: "COMPLETED",
            start_date: null,
            end_date: null,
            season_year: 2026,
          },
        ]}
      />,
    );
    expect(html).toContain("Event CIR Rankings · Pacific Stage 2");
    expect(html).toContain(">T1<");
    expect(html).toContain(">Pacific<");
    expect(html).toContain(">Pacific Stage 2<");
    expect(html).toContain(`href="/players/player-1?event=${eventId}"`);
    expect(html).toContain("Event rounds");
    expect(html).toContain(">Sample<");
    expect(html).not.toContain("Include provisional");
  });

  it("highlights the main role and keeps other played roles visible", () => {
    const html = renderToStaticMarkup(
      <CirRankings
        players={[
          {
            ...player(1),
            role: "Controller",
            roles: [
              { role: "Controller", rounds: 600, share: 0.6, is_main: true },
              { role: "Sentinel", rounds: 400, share: 0.4, is_main: false },
            ],
          },
        ]}
        includeProvisional={false}
        tooltip="CIR"
      />,
    );
    expect(html).toContain("Controller");
    expect(html).toContain("Sentinel");
    expect(html).toContain("Main role Controller, also Sentinel");
    expect(html).toContain("font-medium text-foreground");
  });

  it("shows a dash when team is missing", () => {
    const html = renderToStaticMarkup(
      <CirRankings
        players={[{ ...player(1), team: null }]}
        includeProvisional={false}
        tooltip="CIR"
      />,
    );
    expect(html).toContain(">—<");
  });
});
