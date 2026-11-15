CREATE TABLE IF NOT EXISTS items (
  id   TEXT    NOT NULL,   -- SHA-256 of the sync code (hex)
  k    TEXT    NOT NULL,   -- hash of the item (company) name
  u    INTEGER NOT NULL,   -- client modified time (ms), last writer wins
  s    INTEGER NOT NULL,   -- server write time (ms), used for incremental pulls
  data TEXT    NOT NULL,   -- encrypted blob
  PRIMARY KEY (id, k)
);
CREATE INDEX IF NOT EXISTS items_by_server_time ON items (id, s);
