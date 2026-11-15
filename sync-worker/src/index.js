// Plumb sync server: a Cloudflare Worker backed by D1.
// It stores opaque, end-to-end encrypted blobs. The server never sees sync codes,
// company names or any financial data: the browser encrypts everything with a key
// derived from the sync code, and identifies the account by a one-way hash of it.
//
// API (all JSON):
//   GET    /v1/:id?since=<serverMs>   -> { items: [{k, u, s, data}], now }
//   PUT    /v1/:id/:k   {u, data}      -> { ok, s }   (last writer by client time `u` wins)
// :id = 64 hex chars (SHA-256 of the code), :k = 32 hex chars (hash of the item name)

const MAX_BODY = 1_500_000;   // bytes per item
const MAX_ITEMS = 300;        // items per sync code

export default {
  async fetch(req, env) {
    const cors = {
      'Access-Control-Allow-Origin': env.ALLOWED_ORIGIN || '*',
      'Access-Control-Allow-Methods': 'GET,PUT,OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Max-Age': '86400',
    };
    const json = (obj, status = 200) => new Response(JSON.stringify(obj), {status, headers: {...cors, 'Content-Type': 'application/json'}});
    if (req.method === 'OPTIONS') return new Response(null, {headers: cors});

    const url = new URL(req.url);
    if (url.pathname === '/' || url.pathname === '/health') return json({ok: true, service: 'plumb-sync'});
    const m = url.pathname.match(/^\/v1\/([0-9a-f]{64})(?:\/([0-9a-f]{32}))?$/);
    if (!m) return json({error: 'not found'}, 404);
    const [, id, k] = m;

    try {
      if (req.method === 'GET' && !k) {
        const since = Number(url.searchParams.get('since')) || 0;
        const {results} = await env.DB.prepare('SELECT k, u, s, data FROM items WHERE id = ? AND s > ? ORDER BY s').bind(id, since).all();
        return json({items: results, now: Date.now()});
      }
      if (req.method === 'PUT' && k) {
        const body = await req.text();
        if (body.length > MAX_BODY) return json({error: 'item too large'}, 413);
        let p; try { p = JSON.parse(body); } catch { return json({error: 'bad json'}, 400); }
        if (typeof p.u !== 'number' || typeof p.data !== 'string' || p.data.length > MAX_BODY) return json({error: 'bad item'}, 400);
        const exists = await env.DB.prepare('SELECT 1 FROM items WHERE id = ? AND k = ?').bind(id, k).first();
        if (!exists) {
          const c = await env.DB.prepare('SELECT COUNT(*) AS n FROM items WHERE id = ?').bind(id).first();
          if (c && c.n >= MAX_ITEMS) return json({error: 'too many items'}, 429);
        }
        const s = Date.now();
        const r = await env.DB.prepare(
          'INSERT INTO items (id, k, u, s, data) VALUES (?, ?, ?, ?, ?) ' +
          'ON CONFLICT(id, k) DO UPDATE SET u = excluded.u, s = excluded.s, data = excluded.data WHERE excluded.u >= items.u'
        ).bind(id, k, p.u, s, p.data).run();
        return json({ok: true, s, applied: r.meta.changes > 0});
      }
      return json({error: 'method not allowed'}, 405);
    } catch (e) {
      return json({error: 'server error'}, 500);
    }
  },
};
