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
| `data/pc4.json` | Amsterdam PC4 → neighbourhood + approximate centroid, used to place pins instantly before geocoding resolves. Grows as new postcodes appear; `build.py` warns when one is missing. |
| `docs/index.html` | The built page. **GitHub Pages serves `main` → `/docs`.** |
| `board.json` | Shared board state — **lives on the `board` branch**, not here. |

## Rebuilding

```sh
python3 src/parse_emails.py "<gmail-thread-dumps>/*.txt" data/listings.json
python3 src/enrich.py --only-missing     # or bare, to refresh sale statuses
python3 src/build.py
```

Three constants in `src/build.py` decide what starts in Archived:

| constant | value | effect |
|---|---|---|
| `CUTOFF` | `2026-09-10` | first seen earlier → Archived |
| `MIN_M2` | `70` | under 70 m² → Archived |
| `MIN_BEDROOMS` | `2` | one bedroom or fewer → Archived |
| `WITHDRAWN` | `Ingetrokken` | pulled off the market → Archived |

They set the **default** stage only. A card either of us has actually moved
carries its own stage in `board.json` and keeps it, so a 64 m² flat we liked
anyway stays liked — which is why archiving is done by rebuilding rather than
by writing to the board. An *unknown* bedroom count counts as unknown, not as
too small: a parsing miss leaves a flat in Backlog rather than hiding it.

Because `status` is refreshed by `enrich.py`, the withdrawn rule also catches a
listing pulled *after* it reached Backlog — the next rebuild drops it out.
Sold and under-offer are deliberately not archived: those still get struck
through on the card, but they stay where they are.

### Postcode areas

Widening the neighbourhood selection on move.nl needs no code change: the
pipeline reacts to whatever postcodes turn up in the listings, not to what's
selected. The one manual step is `data/pc4.json`, which supplies the
neighbourhood *name* — there's no other source for it — and an approximate
centroid used to place a pin before the browser geocodes the exact address.

`build.py` prints a `WARNING: N postcode area(s) missing from data/pc4.json`
when a listing's PC4 has no entry, and the refresh routine is told to clear it
before committing. Without an entry a listing still builds and still lands in
the right column; its cards just read "Amsterdam 1013" instead of a
neighbourhood, and it has no pin until that browser geocodes it.

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

Each column's sort order (`sorts`) and the column colours (`colors`) ride along
in the same file, each with a single timestamp for the whole set: they change
rarely, so newest-wins across the whole map is enough.
Clicking a column's dot opens a colour picker and recolours that column on both
boards; the header, card stripes and map pins all read the same CSS variable, so
a custom colour applies in light and dark alike. "Reset colours" in the Sync
panel puts every column back to its theme-aware default.

The sort picker under each column heading offers price, €/m², size, bedrooms,
energy class, area and garden/terrace-first, defaulting to newest-listed. Each
column is independent, ties fall back to newest-first so a coarse sort still
reads sensibly within a group, and a listing with no energy class sorts last
rather than first. Energy, garden and terrace read the *effective* value, so a
figure corrected by hand in the Edit panel is what sorting uses.

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

An hourly routine (:15) reads new AVT digests, enriches, rebuilds and pushes.
Its prompt lives in `routine.md`.

### Knowing the routines are alive

Both routines end every run — including runs where they found nothing — with

```sh
python3 src/heartbeat.py <listing_refresh|viewing_tracker> "<one-line summary>"
```

which writes `health.json` on the **`board`** branch (there, not `main`, so a
heartbeat never triggers a Pages rebuild). The board's header reads it and shows
how long ago each routine last reported in, turning red past 2.5 hours or on a
run that reported failure. Hovering gives the last summary from each.

This exists because a routine that has silently stopped and a routine that ran
and found nothing look identical from the outside, and the platform's own
"succeeded" only means the session exited cleanly — not that the work happened.
One such silent no-op cost a full day of debugging.

### Viewing tracker

A second, hourly routine watches for viewing-related email and moves cards
through **Viewing Applied → Viewing Scheduled** on its own. Its prompt lives
in `viewing-routine.md`; state (which requests are already processed, which
listings are awaiting a confirmation) lives in
`data/viewing_tracker_state.json` on `main`.

The two-step flow it's watching for:

1. **Requesting a viewing** sends a "Viewing Request `<address>` in Amsterdam
   with `<agency>`" email from `no-reply@move.nl`. The routine matches the
   address against `data/listings.json` and moves the card to Viewing
   Applied, noting which agency it went to.
2. **A confirmation can come from either side.** Usually the agency's reply,
   which lands as a separate thread — its own subject, from
   its own domain, not a reply inside the move.nl thread — so matching is
   by address, never by thread ID. The routine reads that thread and only
   treats it as confirmed once there's a specific date and time **both
   sides have actually settled on**; an agency's opening proposal ("does
   13:45 work?") is not itself a confirmation. Once confirmed, the card
   moves to Viewing Scheduled with a note carrying the date, time and the
   agency's email — written into the existing free-text `note` field
   (`📅 Confirmed: ...`), so no new schema or UI was needed for this.
   But often nothing arrives from the agency at all: one of us phones them
   or books online and then just mails the other ("Viewing scheduled on this
   Friday, 10am"). The routine therefore reads our own mail to each other as
   a confirmation source too, and resolves a relative weekday against the
   **send date of that message** — Pythagorasstraat 8 3 was booked that way
   and would otherwise have sat in Viewing Applied indefinitely.

   Two traps it is told about explicitly: the `Voorkeursmomenten` in a
   move.nl request are *preferred* slots, never a booking (that listing asked
   for Mon 21 Sep and was actually seen Fri 25 Sep), and an ambiguous
   relative date is never guessed — the card stays in Viewing Applied and a
   human is asked.

It writes to `board.json` through `src/board_patch.py`, never by hand: the
script fetches the `board` branch's current head, merges the patch in, and
retries once if a browser's own write raced it. `viewing_line` in a patch
becomes the note's first line (replacing a previous machine-written line, one
starting with ✉️ or 📅) while leaving anything a human typed below it alone.

It only moves a card **forward** — Backlog/Liked → Applied → Scheduled — and
never touches one a human has already moved to Visited, Disliked, or
Archived; it flags those in its notification instead of reviving them. It
never invents a date or time that isn't literally in an email.

#### Calendar events

Confirming a viewing (and only confirming — never a proposal) also puts it in
Google Calendar as `Apt Viewing: <address>`, 15 minutes — the standard viewing
slot here — unless the agency actually stated an end time, with
katiazoritch@gmail.com invited. The description leads with the
move.nl link, then address, agency, contact name, phone and email taken from the
confirming email — a missing phone is omitted, never guessed.

#### Forwarding to Katia

The agencies only ever write to Eduard, so every agency reply — proposal,
confirmation, reschedule, rejection — is forwarded to Katia with Eduard in cc,
and both copies are marked read. `forwarded_message_ids` in the state file is
what stops the hourly routine re-forwarding the same mail.

Marking as read needs the Gmail connector's `gmail.modify` scope, which the
current authorisation does not include; the forward itself works, so the
routine treats a refused mark-as-read as a note, never a failed run.

`calendar_events` in `data/viewing_tracker_state.json` maps listing id → event
id, which is what stops an hourly routine from creating the same event over and
over; it must be committed in the same push as the move that created the event.
If the agency later moves the appointment, the stored event is updated rather
than duplicated. The account attaches a Google Meet link to new events by
itself and the API won't remove it — harmless here, and ignored.
