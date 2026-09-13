# Amsterdam house hunt

A kanban board and map over the apartments AVT Makelaars emails to us, so Eduard
and Katia can work the same shortlist instead of two inboxes.

**Board: https://eduryev.github.io/amsterdam_house/**

## How it fits together

```
Gmail digests ──parse_emails.py──> data/listings.json ──build.py──> docs/index.html
                                          ▲
move.nl listing pages ──enrich.py─────────┘
```

| path | what it is |
|---|---|
| `src/parse_emails.py` | Parses AVT "Er zijn nieuwe objecten gevonden" digests into one deduplicated record per address. Handles `Vraagprijs:` and `Koopsom:`, and the `living m² / plot m²` form used for houses. |
| `src/enrich.py` | Reads each move.nl listing page for what the emails omit: energy class, garden/terrace, sale status, tenure. Resumable. |
| `src/build.py` | Inlines the data into one self-contained page. |
| `src/template.html` | The page. `__LISTINGS__`, `__PC4__`, `__BUILT__`, `__CUTOFF__` are substituted at build time. |
| `data/listings.json` | The listings. |
| `data/pc4.json` | Amsterdam PC4 → neighbourhood + approximate centroid, used to place pins instantly before geocoding resolves. |
| `docs/index.html` | The built page. **GitHub Pages serves `main` → `/docs`.** |
| `board.json` | Shared board state — **lives on the `board` branch**, not here. |

## Rebuilding

```sh
python3 src/parse_emails.py "<gmail-thread-dumps>/*.txt" data/listings.json
python3 src/enrich.py --only-missing     # or bare, to refresh sale statuses
python3 src/build.py
```

`CUTOFF` in `src/build.py` (currently `2026-09-10`) decides what starts in Archived.

## Where the fields come from

Address, move.nl link, price, m², rooms/bedrooms and photo come from the emails.
Energy class, garden (G), terrace (T), sale status and tenure do **not** — those
come from `enrich.py` reading the listing page.

The listing pages server-render a structured `kenmerk-label` / `kenmerk-value`
table, so plain HTTP is enough; no browser, no JS execution. This needs the cloud
environment's network policy to allow `move.nl` (**Custom** network access with
`move.nl` and `*.move.nl`, plus "Also include default list of common package
managers"). Without it every fetch fails and the fields stay blank.

Two traps in that markup, both of which produced silently wrong data first time:

- **`Balkon` is filed under `Indeling`, not `Buitenruimte`.** A section-scoped
  lookup misses every balcony. Match labels across all sections.
- **`Tuin` names the *type* of outdoor space.** `Zonneterras` is a terrace, not a
  garden; `Geen tuin` is neither. Classify the value, don't just test presence.

Scraped values are **defaults**. Anything set in the board's Edit panel wins,
including deliberately clearing a field; the panel shows which it is displaying.

## Sharing the board

Board state — column, energy, G/T, notes — lives in `board.json` on the **`board`
branch**. Every open board polls it every 10 seconds and merges by per-listing
timestamp, so the most recent edit to a given listing wins, and only for that
listing. An edit pushes within half a second rather than waiting out the interval.
`localStorage` keeps a local copy, so the board works offline and catches up later.

It sits on its own branch deliberately: `main` serves GitHub Pages, and a commit
every time someone moves a card would rebuild the site and hit the ~10 builds/hour
limit.

Reading needs nothing — the repo is public, so a board with no token polls
`raw.githubusercontent.com` read-only. **Saving** needs a
[fine-grained token](https://github.com/settings/personal-access-tokens) limited to
`eduryev/amsterdam_house` with **Contents: Read and write**, pasted once into the
Sync panel and kept only in that browser.

Concurrent writes use the blob SHA for optimistic concurrency: a write that loses
the race is rejected, and the next tick re-reads, merges and retries.

> A token in browser storage is readable by anything served from the same origin
> (`eduryev.github.io`). Keep it scoped to this repository, set an expiry, and
> revoke it when we've bought somewhere.

## Automation

A daily routine at 08:00 Amsterdam reads new AVT digests, enriches, rebuilds and
pushes. Its prompt lives in `routine.md`.
