import { Suspense } from "react";
import type { Metadata } from "next";

import { CompareWorkspace } from "@/components/compare-workspace";
import { parseCompareIds } from "@/lib/compare";

export const metadata: Metadata = {
  title: "Compare",
};

type ComparePageProps = {
  searchParams: Promise<{ ids?: string | string[] }>;
};

export default async function ComparePage({ searchParams }: ComparePageProps) {
  const params = await searchParams;
  const ids = parseCompareIds(params.ids);

  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading compare…</p>}>
      <CompareWorkspace initialIds={ids} />
    </Suspense>
  );
}
