# Dashboard overrides

> Overrides `MASTER.md` for the player operations dashboard (`/`).

- This is a **data console**, not a marketing landing page. Skip testimonials, pricing, and “start trial”.
- Lead with API health + roster table. Metrics are aggregates from `/players`.
- Do **not** label data as live. Show API health (`ok` / `degraded` / offline) only.
- Tables: `overflow-x-auto` on small screens; card layout is a fallback, not the default at `md+`.
- Primary CTA in the header is **Compare** (requires 2+ selected players).
- Hover on rows: background only. No scale transforms.
