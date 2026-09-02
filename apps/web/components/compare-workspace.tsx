"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AlertBanner } from "@/components/alert-banner";
import { CompareDrivers } from "@/components/compare-drivers";
import { ComparePlayerCard } from "@/components/compare-player-card";
import { CompareScouting } from "@/components/compare-scouting";
import { CompareSelector } from "@/components/compare-selector";
import { fetchComparison, fetchPlayerCir, fetchPlayerDetail } from "@/lib/api";
import {
  MAX_COMPARE_PLAYERS,
  addCompareId,
  compareCardGridClass,
  compareEmptyMessage,
  compareHref,
  compareOptionFromCir,
  compareOptionFromDetail,
  compareOptionFromEntry,
  mergeCompareOptions,
  parseCompareIds,
  pendingCompareOption,
  removeCompareId,
  unknownCompareOption,
} from "@/lib/compare";
import type { PlayerCompareEntry, PlayerOption } from "@/lib/types";

type CompareWorkspaceProps = {
  initialIds: string[];
};

export function CompareWorkspace({ initialIds }: CompareWorkspaceProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const ids = useMemo(() => {
    const fromUrl = parseCompareIds(searchParams.getAll("ids"));
    if (fromUrl.length > 0) {
      return fromUrl.slice(0, MAX_COMPARE_PLAYERS);
    }
    return initialIds.slice(0, MAX_COMPARE_PLAYERS);
  }, [initialIds, searchParams]);

  const idsKey = ids.join(",");
  const [chips, setChips] = useState<PlayerOption[]>([]);
  const [comparison, setComparison] = useState<{
    players: PlayerCompareEntry[];
    notes: string;
    key: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  function commit(next: string[]) {
    router.replace(compareHref(next), { scroll: false });
  }

  useEffect(() => {
    if (ids.length === 0) {
      return;
    }
    let cancelled = false;
    void Promise.all(ids.map((id) => resolveSelectedChip(id))).then((resolved) => {
      if (!cancelled) {
        setChips((current) => mergeCompareOptions(current, resolved));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [ids, idsKey]);

  useEffect(() => {
    if (ids.length < 2) {
      return;
    }
    const key = idsKey;
    let cancelled = false;
    fetchComparison(ids)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setComparison({ players: payload.players, notes: payload.notes, key });
        setError(null);
        setChips((current) =>
          mergeCompareOptions(current, payload.players.map(compareOptionFromEntry)),
        );
      })
      .catch(() => {
        if (!cancelled) {
          setError("The comparison request failed. Check the selected IDs and try again.");
          setComparison({ players: [], notes: "", key });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [ids, idsKey]);

  const loading = ids.length >= 2 && comparison?.key !== idsKey;
  const players = useMemo(() => {
    if (ids.length >= 2 && comparison?.key === idsKey) {
      return comparison.players;
    }
    return [];
  }, [comparison, ids.length, idsKey]);
  const notes = comparison?.key === idsKey ? comparison.notes : "";

  const selectedChips = useMemo(
    () => ids.map((id) => chips.find((chip) => chip.id === id) ?? pendingCompareOption(id)),
    [chips, ids],
  );

  return (
    <div className="space-y-4">
      <CompareSelector
        selectedIds={ids}
        selectedChips={selectedChips}
        onAdd={(player) => {
          const result = addCompareId(ids, player.id);
          setAddError(result.error);
          if (result.error == null) {
            setChips((current) =>
              current.some((item) => item.id === player.id) ? current : [...current, player],
            );
            commit(result.ids);
          }
          return result.error;
        }}
        onRemove={(id) => {
          setAddError(null);
          commit(removeCompareId(ids, id));
        }}
      />
      {addError ? (
        <p className="text-sm text-muted-foreground" role="status">
          {addError}
        </p>
      ) : null}
      {ids.length < 2 ? (
        <div className="rounded-xl bg-muted/40 p-4">
          <p className="text-sm">{compareEmptyMessage(ids.length)}</p>
        </div>
      ) : null}
      {loading ? (
        <p className="text-sm text-muted-foreground" aria-busy="true">
          Loading player comparison…
        </p>
      ) : null}
      {error ? <AlertBanner title={error} /> : null}
      {players.length > 0 ? (
        <>
          <div className={compareCardGridClass(players.length)}>
            {players.map((entry) => (
              <ComparePlayerCard
                key={entry.player.id}
                entry={entry}
                count={players.length}
                onRemove={(id) => commit(removeCompareId(ids, id))}
              />
            ))}
          </div>
          <p className="text-xs text-muted-foreground">{notes}</p>
          <CompareDrivers players={players} />
          <CompareScouting players={players} />
        </>
      ) : null}
    </div>
  );
}

async function resolveSelectedChip(id: string) {
  try {
    const cir = await fetchPlayerCir(id);
    if (cir?.handle) {
      return compareOptionFromCir(cir);
    }
  } catch {
    // Identity lookup still has the handle if CIR is missing.
  }
  try {
    const detail = await fetchPlayerDetail(id);
    if (detail?.player.handle) {
      return compareOptionFromDetail(detail);
    }
  } catch {
    // Fall through to the unknown-player chip.
  }
  return unknownCompareOption(id);
}
