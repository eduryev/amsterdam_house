# Viewing tracker routine

Watches for AVT/move.nl viewing-request emails and the agency replies that
follow them, and moves cards through Viewing Applied → Viewing Scheduled
automatically. Runs hourly.

**Needs the Gmail connector attached** — same as the daily listing-refresh
routine, and granted separately: claude.ai → Routines → this routine →
enable Gmail.

The prompt it runs is below (also the source of truth if it needs recreating).

---

Track apartment viewings for the Amsterdam house-hunt board.

Repository: **eduryev/amsterdam_house**. Read `README.md`'s "Viewing tracker"
section first. `data/listings.json` and `data/viewing_tracker_state.json` live
on `main`; the shared board state, `board.json`, lives on the **`board`**
branch and is written by Eduard's and Katia's browsers every ~10 seconds
while either has the board open — never edit it by hand or with a plain
`git commit`. Always go through `src/board_patch.py`, which handles the
race safely (fetches the branch's current head, merges your patch in,
retries once on a push conflict). Never touch `data/listings.json` or
`docs/index.html` from this routine — that's the other routine's job.

FIRST: check you have Gmail tools (`mcp__Gmail__search_threads`). If not,
notify "The viewing tracker has no Gmail connector attached — enable it at
claude.ai → Routines" and stop.

Load `data/viewing_tracker_state.json` (`{processed_request_ids: [...],
tracking: {<listing_id>: {agency_name, address, requested_at}}}`).

## Step A — new viewing requests

Search `from:no-reply@move.nl subject:"Viewing Request"`. For each thread
whose message id isn't already in `processed_request_ids`:

1. Parse the subject: `Viewing Request <ADDRESS> in Amsterdam with <AGENCY>`
   (strip a trailing period from the agency name).
2. Match `<ADDRESS>` against `data/listings.json` — compare case- and
   whitespace-insensitively; addresses match exactly or not at all, don't
   guess at a fuzzy match. If nothing matches, this is a property found
   outside the AVT feed (it happens — e.g. Javastraat 172 H, via Broersma
   Makelaardij, isn't in our data at all). Don't invent a listing for it;
   collect address + agency + date into an "off-board" list to mention at
   the end, so a human decides whether to add it.
3. On a match, read that listing's **current** stage from `board.json` on
   `board` (`git show origin/board:board.json`, or clone/pull it — read-only,
   no need for board_patch.py here). Only move it if the stage is `backlog`
   or `viewed` (Liked) — i.e. nothing's happened with it yet. If it's already
   `applied` or `scheduled`, this is a request you've already processed;
   just record the message id and move on, no need to touch the board or
   mention it. If it's `disliked`, `archived`, or `visited`, a human has
   already made a call on it — don't revive it; just note it in the "found
   but not moved" list so they know a viewing request exists for it.
4. When you do move it:
   `python3 src/board_patch.py '{"<listing-id>": {"stage": "applied", "viewing_line": "✉️ Viewing requested — <Agency Name>"}}'`
   Then record in `tracking`: `{"<listing-id>": {"agency_name": "...",
   "address": "...", "requested_at": "<email date, YYYY-MM-DD>"}}`.
5. Add the message id to `processed_request_ids` regardless of outcome.

## Step B — checking for confirmation

For every listing in `tracking` whose board.json stage is *still* `applied`
(if a human moved it elsewhere themselves, drop it from `tracking` silently —
not your concern anymore):

1. Search Gmail for that address, excluding move.nl's own address, since
   when the agency's reply, it lands as a **separate thread**, not a reply
   in the move.nl thread — its subject usually looks like "Viewing
   `<address>` ... [ref]" from the agency's own domain:
   `"<address>" -from:no-reply@move.nl after:<requested_at>`
2. Read whatever thread(s) turn up in full, and read them carefully — this
   decision is the one that matters most. A thread with a **specific date
   and time that both sides have actually settled on** — the agency stating
   it's booked/confirmed, or Eduard/Katia having explicitly accepted a
   slot the agency offered, with nothing left hanging — counts as
   confirmed. An agency's opening message proposing a slot and asking "does
   this work for you?" is **not** confirmed by itself, even though it has a
   date and time in it — that's a proposal awaiting a reply. When genuinely
   unsure which of these you're looking at, treat it as **not confirmed**:
   leave the stage at `applied` and say so in your notification for a human
   to judge, rather than guess.
3. **Confirmed** — extract the exact date and time as written (translate a
   Dutch weekday/month for readability; never reformat or infer beyond
   what's on the page) and the confirming email's sender address, then:
   `python3 src/board_patch.py '{"<listing-id>": {"stage": "scheduled", "viewing_line": "📅 Confirmed: <date>, <time> — <Agency Name> (<agency email>)"}}'`
   and remove it from `tracking` — fully resolved.
4. **Proposed, not yet confirmed** — update the note to reflect it, stage
   stays `applied`:
   `python3 src/board_patch.py '{"<listing-id>": {"viewing_line": "✉️ Proposed: <date>, <time> — awaiting confirmation — <Agency Name>"}}'`
   Keep it in `tracking`.
5. **Nothing new** — leave it, keep it in `tracking`.

Never invent a date, time, or agency email that isn't literally in the
email text.

## Finishing

Save `data/viewing_tracker_state.json`, commit and push to `main` (plain git
is fine here — this file isn't touched by anyone else, unlike board.json).

Never send a push notification. Record everything (moves, off-board finds,
already-archived hits, proposals, confirmations) in the state file and commit
message only.
