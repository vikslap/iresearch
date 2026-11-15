# Plumb sync server

A tiny Cloudflare Worker + D1 database that lets Plumb sync saved companies,
SOIC answers, edits and price history across devices.

Everything is encrypted in the browser with a key derived from your sync code
before it is uploaded. The server only stores opaque blobs keyed by a hash of
the code, so it cannot read company names or numbers.

## Deploy (about 5 minutes)

```bash
cd sync-worker
npx wrangler login                              # once
npx wrangler d1 create plumb-sync               # copy the database_id it prints
# paste that id into wrangler.toml (database_id = "...")
npx wrangler d1 execute plumb-sync --remote --file=schema.sql
npx wrangler deploy                             # prints https://plumb-sync.<you>.workers.dev
```

Open the printed URL: it should answer `{"ok":true,"service":"plumb-sync"}`.
Then put that URL in Plumb (Sync → server URL), or set `SYNC_DEFAULT_URL` in `index.html`.

Free-tier limits are far above what one person's research uses.
