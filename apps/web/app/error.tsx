"use client";

import { useEffect } from "react";
import { AlertBanner } from "@/components/alert-banner";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <AlertBanner title="This page failed to load.">
      <p>Retry the request, or return to rankings if the problem continues.</p>
      <button
        type="button"
        onClick={reset}
        className="mt-2 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-on-accent transition-opacity duration-200 hover:opacity-90"
      >
        Retry
      </button>
    </AlertBanner>
  );
}
