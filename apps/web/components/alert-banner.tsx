"use client";

import { WarningIcon } from "@phosphor-icons/react";
import type { ReactNode } from "react";

type AlertBannerProps = {
  title: string;
  children?: ReactNode;
};

export function AlertBanner({ title, children }: AlertBannerProps) {
  return (
    <div
      role="alert"
      className="glass-panel flex gap-2 rounded-xl p-3 text-sm text-foreground"
    >
      <WarningIcon className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
      <div>
        <p className="font-medium">{title}</p>
        {children ? <div className="mt-1 text-muted-foreground">{children}</div> : null}
      </div>
    </div>
  );
}
