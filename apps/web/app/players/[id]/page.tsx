import Link from "next/link";
import type { Metadata } from "next";

import { AlertBanner } from "@/components/alert-banner";
import { PlayerDossier } from "@/components/player-dossier";
import { fetchPlayerCir, fetchPlayerDetail } from "@/lib/api";

type PlayerPageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: PlayerPageProps): Promise<Metadata> {
  const { id } = await params;
  const player = await fetchPlayerDetail(id).catch(() => null);
  return {
    title: player?.player.handle ?? "Player not found",
  };
}

export default async function PlayerPage({ params }: PlayerPageProps) {
  const { id } = await params;
  let detail;
  let cir;
  try {
    [detail, cir] = await Promise.all([fetchPlayerDetail(id), fetchPlayerCir(id)]);
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

  return <PlayerDossier detail={detail} cir={cir} />;
}
