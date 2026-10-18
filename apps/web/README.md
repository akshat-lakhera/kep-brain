# KEP Brain web app

The Next.js front end. It renders the Ask, Explore, Audit, Tools and Memory pages and talks to the KEP Brain API only through its own same-origin proxy.

## Run it

```bash
pnpm install
API_INTERNAL_URL=http://localhost:8000 pnpm dev   # http://localhost:3000
```

- `API_INTERNAL_URL` is the API the server-side proxy forwards to (default `http://localhost:8000`).
- `pnpm build` then `pnpm start` runs the production build; the Dockerfile in this directory does the same for the compose stack.
- Checks: `npx next typegen`, `npx tsc --noEmit -p .`, `npx eslint src`.
