import Link from "next/link";
import type { Metadata } from "next";

import { AlertBanner } from "@/components/alert-banner";
import { PlayerDossier } from "@/components/player-dossier";
import { fetchPlayerCir, fetchPlayerDetail } from "@/lib/api";

type PlayerPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ event?: string | string[] }>;
};

function firstParam(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
  );
}

export async function generateMetadata({ params }: PlayerPageProps): Promise<Metadata> {
  const { id } = await params;
  const player = await fetchPlayerDetail(id).catch(() => null);
  return {
    title: player?.player.handle ?? "Player not found",
  };
}

export default async function PlayerPage({ params, searchParams }: PlayerPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const eventRaw = firstParam(query.event);
  const eventId = eventRaw && isUuid(eventRaw) ? eventRaw : null;

  let detail;
  let cir;
  try {
    [detail, cir] = await Promise.all([
      fetchPlayerDetail(id, { eventId }),
      fetchPlayerCir(id, { eventId }),
    ]);
  } catch {
    return (
      <AlertBanner title="Could not load this player.">
        The API did not respond. Return to the{" "}
        <Link href="/rankings" className="underline underline-offset-2 hover:text-accent">
          rankings
        </Link>
        .
      </AlertBanner>
    );
  }

  if (detail == null) {
    return (
      <AlertBanner title={`No player matches “${id}”.`}>
        Check the ID, or go back to the{" "}
        <Link href="/rankings" className="underline underline-offset-2 hover:text-accent">
          rankings
        </Link>
        .
      </AlertBanner>
    );
  }

  return <PlayerDossier detail={detail} cir={cir} eventId={eventId} />;
}
