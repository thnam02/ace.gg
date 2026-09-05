import Link from "next/link";
import type { Metadata } from "next";

import { AlertBanner } from "@/components/alert-banner";
import { CirRankings } from "@/components/cir-rankings";
import { fetchCirMetadata, fetchCirRankings, fetchEvents } from "@/lib/api";
import {
  parseRankingSearchParams,
  rankingHref,
} from "@/lib/ranking-filters";
import type { EventSummary } from "@/lib/types";

export const metadata: Metadata = {
  title: "Rankings",
};

type RankingsPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function scopeLabel(scope: Awaited<ReturnType<typeof fetchCirRankings>>["scope"]): string | null {
  if (scope == null) {
    return null;
  }
  if (typeof scope === "string") {
    return null;
  }
  return scope.label || null;
}

export default async function RankingsPage({ searchParams }: RankingsPageProps) {
  const params = await searchParams;
  const { filters, includeProvisional } = parseRankingSearchParams(params);
  const eventScoped = filters.eventId != null;

  let rankings = null;
  let cirMetadata = null;
  let events: EventSummary[] = [];
  try {
    const [rankingsResult, metadataResult, eventsResult] = await Promise.all([
      fetchCirRankings({
        eventId: filters.eventId,
        includeProvisional: includeProvisional || eventScoped,
        includeLowSample: eventScoped,
        minRounds: filters.minRounds,
        role: filters.role,
        tier: eventScoped ? null : filters.tier,
        region: eventScoped ? null : filters.region,
        sort: filters.sort,
        order: filters.order,
      }),
      fetchCirMetadata(),
      fetchEvents({
        year: 2026,
        tier: filters.tier,
        region: filters.region,
        limit: 200,
      }).catch(() => ({ total: 0, events: [] as EventSummary[] })),
    ]);
    rankings = rankingsResult;
    cirMetadata = metadataResult;
    events = eventsResult.events;
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

  const eventName =
    rankings.event_name ??
    scopeLabel(rankings.scope) ??
    events.find((item) => item.id === filters.eventId)?.name ??
    null;
  const eventStatus =
    rankings.event_status ??
    (typeof rankings.scope === "object" ? rankings.scope?.status : null) ??
    events.find((item) => item.id === filters.eventId)?.status ??
    null;

  const title = eventScoped
    ? `Event CIR Rankings${eventName ? ` · ${eventName}` : ""}`
    : "CIR rankings";

  const provisionalOn = rankingHref(filters, { includeProvisional: true });
  const provisionalOff = rankingHref(
    { ...filters, eventId: null },
    { includeProvisional: false },
  );

  return (
    <div className="space-y-3">
      <header className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">
          {eventScoped
            ? "Stats shown below are calculated from this event only. CIR uses the frozen v0.2 reference population."
            : "Filter the current CIR pool by tier, region, role, and event. Sort by combat or scouting metrics."}
        </p>
      </header>

      <CirRankings
        players={rankings.players}
        total={rankings.total}
        includeProvisional={includeProvisional || eventScoped}
        tooltip={
          eventScoped
            ? "This CIR score is calculated from the selected event only, using the frozen CIR v0.2 reference population."
            : (cirMetadata?.tooltip ?? "")
        }
        title={title}
        initialFilters={filters}
        events={events}
        eventName={eventName}
        eventStatus={eventStatus}
        eventScoped={eventScoped}
        toggleHref={{
          on: provisionalOn,
          off: provisionalOff,
        }}
      />
    </div>
  );
}
