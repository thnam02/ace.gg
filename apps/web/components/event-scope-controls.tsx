"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";

import { fetchEvents } from "@/lib/api";
import { RANKING_REGIONS } from "@/lib/ranking-filters";
import type { EventSummary } from "@/lib/types";

type EventScopeControlsProps = {
  selectedRegion: string | null;
  selectedVlrEventId: number | null;
  includeProvisional: boolean;
  initialEvents?: EventSummary[];
};

const controlClass =
  "rounded-md border border-white/10 bg-muted/60 px-2 py-1.5 text-xs text-foreground";

export function EventScopeControls({
  selectedRegion,
  selectedVlrEventId,
  includeProvisional,
  initialEvents = [],
}: EventScopeControlsProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [region, setRegion] = useState<string | null>(selectedRegion);
  const [events, setEvents] = useState<EventSummary[]>(initialEvents);
  const [loadingEvents, setLoadingEvents] = useState(false);

  useEffect(() => {
    setRegion(selectedRegion);
  }, [selectedRegion]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoadingEvents(true);
      try {
        const response = await fetchEvents({
          region: region,
          limit: 200,
        });
        if (!cancelled) {
          setEvents(response.events);
        }
      } catch {
        if (!cancelled) {
          setEvents([]);
        }
      } finally {
        if (!cancelled) {
          setLoadingEvents(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [region]);

  const eventOptions = useMemo(() => events, [events]);

  function pushScope(next: {
    region: string | null;
    vlrEventId: number | null;
  }) {
    const params = new URLSearchParams();
    if (includeProvisional || next.vlrEventId != null) {
      params.set("include_provisional", "1");
    }
    if (next.region) {
      params.set("region", next.region);
    }
    if (next.vlrEventId != null) {
      params.set("vlr_event_id", String(next.vlrEventId));
    }
    const query = params.toString();
    startTransition(() => {
      router.push(query ? `/rankings?${query}` : "/rankings");
    });
  }

  return (
    <div className="glass-panel flex flex-wrap items-end gap-3 rounded-xl px-3 py-3">
      <label className="grid gap-1">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Region
        </span>
        <select
          value={region ?? ""}
          disabled={pending}
          onChange={(event) => {
            const nextRegion = event.target.value || null;
            setRegion(nextRegion);
            pushScope({ region: nextRegion, vlrEventId: null });
          }}
          className={controlClass}
        >
          <option value="">All regions</option>
          {RANKING_REGIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
      <label className="grid min-w-[16rem] flex-1 gap-1">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Event
        </span>
        <select
          value={selectedVlrEventId ?? ""}
          disabled={pending || loadingEvents}
          onChange={(event) => {
            const raw = event.target.value;
            pushScope({
              region,
              vlrEventId: raw ? Number(raw) : null,
            });
          }}
          className={controlClass}
        >
          <option value="">Season CIR (all events)</option>
          {eventOptions.map((item) => (
            <option key={item.id} value={item.vlr_event_id}>
              {item.name}
              {item.tier ? ` · ${item.tier}` : ""}
            </option>
          ))}
        </select>
      </label>
      {selectedVlrEventId != null ? (
        <button
          type="button"
          disabled={pending}
          onClick={() => pushScope({ region, vlrEventId: null })}
          className={`${controlClass} text-muted-foreground transition-colors hover:text-foreground`}
        >
          Clear event
        </button>
      ) : null}
    </div>
  );
}
