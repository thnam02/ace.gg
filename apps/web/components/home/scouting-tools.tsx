import Link from "next/link";
import { ArrowsLeftRightIcon, TrophyIcon, UserIcon } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";

const TOOLS: {
  title: string;
  body: string;
  href: string;
  cta: string;
  icon: ReactNode;
}[] = [
  {
    title: "Rankings",
    body: "Explore player rankings across roles, tiers and regions.",
    href: "/rankings",
    cta: "View rankings",
    icon: <TrophyIcon className="size-5 text-muted-foreground" aria-hidden="true" />,
  },
  {
    title: "Compare",
    body: "Compare up to four players side-by-side using CIR drivers and scouting stats.",
    href: "/compare",
    cta: "Compare players",
    icon: <ArrowsLeftRightIcon className="size-5 text-muted-foreground" aria-hidden="true" />,
  },
  {
    title: "Player profiles",
    body: "Understand why a player scores the way they do, then inspect combat, opening and support stats.",
    href: "#player-search",
    cta: "Find a player",
    icon: <UserIcon className="size-5 text-muted-foreground" aria-hidden="true" />,
  },
];

export function ScoutingTools() {
  return (
    <section aria-labelledby="scouting-tools-heading" className="space-y-4">
      <h2
        id="scouting-tools-heading"
        className="font-sans text-2xl font-semibold tracking-tight sm:text-[28px]"
      >
        Scouting tools
      </h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {TOOLS.map(({ title, body, href, cta, icon }) => (
          <article key={title} className="rounded-xl border border-white/10 bg-card p-4 sm:p-5">
            {icon}
            <h3 className="mt-3 font-sans text-base font-semibold tracking-tight">{title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{body}</p>
            <Link
              href={href}
              className="mt-4 inline-flex min-h-10 items-center text-sm font-medium underline-offset-4 hover:underline"
            >
              {cta} →
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
