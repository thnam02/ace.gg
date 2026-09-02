import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/status-badge";

describe("StatusBadge", () => {
  it("hides API/database status from navigation when show is false", () => {
    const html = renderToStaticMarkup(
      <StatusBadge health={{ status: "ok", service: "api", database: "connected" }} show={false} />,
    );
    expect(html).toBe("");
  });

  it("keeps a compact status indicator in development", () => {
    const html = renderToStaticMarkup(
      <StatusBadge health={{ status: "ok", service: "api", database: "connected" }} show />,
    );
    expect(html).toContain("API");
    expect(html).toContain("API ok · database connected");
    expect(html).not.toContain("API ok · database connected</p>");
  });
});
