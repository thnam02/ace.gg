# ACE.gg web

Next.js app for homepage, CIR rankings, player pages, and compare.

```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000. The API must be on http://localhost:8000 (or whatever `API_URL` / `NEXT_PUBLIC_API_URL` point at).

Browser search and compare call **`/scout-api/*`**, which proxies to the API and applies the visitor rate limit. Server-rendered pages fetch the API origin directly.

```bash
npm test
npm run typecheck
npm run lint
```

Vercel: root directory `apps/web`, branch `main`. Env is documented in [deploy/README.md](../../deploy/README.md).
