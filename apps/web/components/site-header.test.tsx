import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { SiteHeader } from "@/components/site-header";
import { BRAND } from "@/lib/brand";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
    className?: string;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/image", () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    // Test double for next/image.
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} />
  ),
}));

describe("SiteHeader", () => {
  it("renders ACE.gg branding from the shared brand config", () => {
    const html = renderToStaticMarkup(<SiteHeader health={null} />);
    expect(html).toContain(BRAND.name);
    expect(html).toContain(BRAND.logoSrc);
    expect(html).not.toContain("VALORANT Scout");
    expect(html).toContain("Rankings");
    expect(html).toContain("Compare");
  });
});
