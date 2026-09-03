import Link from "next/link";
import type { Metadata } from "next";

import { AlertBanner } from "@/components/alert-banner";
import { CirRankings } from "@/components/cir-rankings";
import { EventScopeControls } from "@/components/event-scope-controls";
import {
  fetchCirMetadata,
  fetchCirRankings,
  fetchEventCirRankings,
  fetchEvents,
} from "@/lib/api";
import { parseFlag } from "@/lib/compare";
import { RANKING_REGIONS } from "@/lib/ranking-filters";

export const metadata: Metadata = {
  title: "Rankings",
};

type RankingsPageProps = {
  searchParams: Promise<{
    include_provisional?: string | string[];
    region?: string | string[];
    vlr_event_id?: string | string[];
  }>;
};

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}

function parseRegion(raw: string | null): string | null {
  if (!raw) {
    return null;
  }
  return RANKING_REGIONS.includes(raw as (typeof RANKING_REGIONS)[number]) ? raw : null;
}

function parseVlrEventId(raw: string | null): number | null {
  if (!raw) {
    return null;
  }
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}

export default async function RankingsPage({ searchParams }: RankingsPageProps) {
  const params = await searchParams;
  const includeProvisional = parseFlag(params.include_provisional);
  const region = parseRegion(firstParam(params.region));
  const vlrEventId = parseVlrEventId(firstParam(params.vlr_event_id));
  const eventScoped = vlrEventId != null;

  let rankings = null;
  let cirMetadata = null;
  let events = null;
  try {
    [rankings, cirMetadata, events] = await Promise.all([
      eventScoped
        ? fetchEventCirRankings({
            vlrEventId: vlrEventId!,
            includeProvisional: true,
            includeLowSample: true,
          })
        : fetchCirRankings({ includeProvisional }),
      fetchCirMetadata(),
      fetchEvents({ region, limit: 200 }),
    ]);
  } catch {
    return (
      <AlertBanner title="Could not load CIR rankings.">
        Return to the{" "}
        <Link href="/" className="underline underline-offset-2 hover:text-accent">
          homepage
        </Link>
        .
      </AlertBanner>
    );
  }

  const toggleBase = new URLSearchParams();
  if (region) {
    toggleBase.set("region", region);
  }
  if (vlrEventId != null) {
    toggleBase.set("vlr_event_id", String(vlrEventId));
  }
  const offQuery = toggleBase.toString();
  toggleBase.set("include_provisional", "1");
  const onQuery = toggleBase.toString();

  return (
    <div className="space-y-3">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">
          {eventScoped ? "Event CIR rankings" : "CIR rankings"}
        </h1>
        <p className="text-sm text-muted-foreground">
          {eventScoped
            ? "Frozen v0.2 CIR scored on maps from the selected event only."
            : "Filter the current CIR pool by tier, region, and role. Or pick a region and event for per-event CIR."}
        </p>
      </header>

      <EventScopeControls
        selectedRegion={region ?? rankings.event_region ?? null}
        selectedVlrEventId={vlrEventId}
        includeProvisional={includeProvisional || eventScoped}
        initialEvents={events.events}
      />

      {eventScoped && rankings.note ? (
        <AlertBanner title={rankings.event_name ?? "Selected event"}>
          {rankings.note}
        </AlertBanner>
      ) : null}

      <CirRankings
        players={rankings.players}
        total={rankings.total}
        includeProvisional={includeProvisional || eventScoped}
        tooltip={cirMetadata?.tooltip ?? ""}
        title={eventScoped ? rankings.event_name ?? "Event CIR" : "CIR rankings"}
        toggleHref={{
          on: `/rankings?${onQuery}`,
          off: offQuery ? `/rankings?${offQuery}` : "/rankings",
        }}
      />
    </div>
  );
}
