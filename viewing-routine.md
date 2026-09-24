# Viewing tracker routine

Watches for AVT/move.nl viewing-request emails and the agency replies that
follow them, moves cards through Viewing Applied → Viewing Scheduled, puts
confirmed viewings in Google Calendar, forwards agency mail to Katia, and
keeps an already-scheduled viewing in step with the email when it moves.
Runs hourly.

**Needs the Gmail and Google Calendar connectors attached** — granted per
routine: claude.ai → Routines → this routine → enable them.

The prompt it runs is below, verbatim, and is the source of truth if it ever
needs recreating. Keep this file and the live routine in sync.

---

Track apartment viewings for the Amsterdam house-hunt board.

Repository: **eduryev/amsterdam_house**. Read `README.md`'s "Viewing tracker" section first. `data/listings.json` and `data/viewing_tracker_state.json` live on `main`; the shared board state, `board.json`, lives on the **`board`** branch and is written by Eduard's and Katia's browsers every ~10 seconds while either has the board open — never edit it by hand or with a plain `git commit`. Always go through `src/board_patch.py`, which handles the race safely (fetches the branch's current head, merges your patch in, retries once on a push conflict). Never touch `data/listings.json` or `docs/index.html` from this routine — that's the other routine's job.

FIRST: check you have Gmail tools (`mcp__Gmail__search_threads`). If not, run

    python3 src/heartbeat.py viewing_tracker --fail "no Gmail connector attached"

then notify "The viewing tracker has no Gmail connector attached — enable it at claude.ai → Routines" and stop.

IMPORTANT, learned from a run that read 8 emails, reasoned about all of them correctly, and then silently threw the result away: "nothing moved on the board" is NOT the same as "nothing happened." Deciding a listing is already archived and shouldn't be revived, or finding an off-board address, is a real, useful outcome — it must still update `data/viewing_tracker_state.json` and still appear in your notification. The ONLY case that's genuinely silent is: zero new "Viewing Request" emails since the last run AND nothing in `tracking` changed at all AND Step D found nothing. If you read even one email this run, you commit the state file and you say what you found, even if the answer is "6 addresses already archived, nothing to do." (Even a fully silent run still writes a heartbeat — see the last section.)

Load `data/viewing_tracker_state.json`:

    {processed_request_ids: [...],
     tracking: {<listing_id>: {agency_name, address, requested_at}},
     calendar_events: {<listing_id>: {event_id, start, summary, past_event_ids?}},
     forwarded_message_ids: [...]}

`calendar_events` and `forwarded_message_ids` may be missing on older state files — treat a missing one as empty. `past_event_ids` lists events for viewings of that listing that already happened and have been superseded by a later, separate appointment; never touch those events again.

## Step A — new viewing requests

Search `from:no-reply@move.nl subject:"Viewing Request"`. For each thread whose message id isn't already in `processed_request_ids`:

1. Parse the subject: `Viewing Request <ADDRESS> in Amsterdam with <AGENCY>`. Strip a trailing sentence-ending period from the agency name, but do NOT strip the period of an abbreviation — "B.V. Deltam Makelaardij o.g." keeps its final period; write it as "Deltam Makelaardij o.g." rather than mangling it to "o.g".
2. Match `<ADDRESS>` against `data/listings.json` — compare case- and whitespace-insensitively; addresses match exactly or not at all, don't guess at a fuzzy match. If nothing matches, this is a property found outside the AVT feed (it happens — e.g. Javastraat 172 H, via Broersma Makelaardij, isn't in our data at all). Don't invent a listing for it; collect address + agency + date into an "off-board" list to mention at the end, so a human decides whether to add it.
3. On a match, read that listing's **current** stage from `board.json` on `board` (`git show origin/board:board.json`, or clone/pull it — read-only, no need for board_patch.py here; its default when unset is `backlog` if `first_seen >= 2026-09-10`, else `archived` — check `src/build.py`'s CUTOFF if that value ever changes). Only move it if the stage is `backlog` or `viewed` (Liked) — i.e. nothing's happened with it yet. If it's already `applied` or `scheduled`, this is a request you've already processed; just record the message id and move on, no need to touch the board or mention it. If it's `disliked`, `archived`, or `visited`, a human has already made a call on it — don't revive it; DO note it in the "found but not moved" list so they know a viewing request exists for it — this is a reportable outcome, not a silent one. **One exception, and only this one: a fresh request for a listing at `visited` is a repeat viewing, so also run Step D for it** (they saw it, liked it, and are going back) — still without changing its stage.
4. When you do move it: `python3 src/board_patch.py '{"<listing-id>": {"stage": "applied", "viewing_line": "✉️ Viewing requested — <Agency Name>"}}'`
   Then record in `tracking`: `{"<listing-id>": {"agency_name": "...", "address": "...", "requested_at": "<email date, YYYY-MM-DD>"}}`.
5. Add the message id to `processed_request_ids` regardless of outcome — matched-and-moved, matched-but-archived, and off-board all count as processed.

**Never read a confirmed time out of the request itself.** The move.nl request quotes Eduard's *preferred* slots under "Voorkeursmomenten" (and in `agbegin=` inside its links). Those are wishes, not bookings — the agency very often books something else entirely. Pythagorasstraat 8 3 asked for Monday 21 Sep 10:00 and was actually viewed on Friday 25 Sep. A time is only confirmed via Step B.

## Step B — checking for confirmation

For every listing in `tracking` whose board.json stage is *still* `applied` (if a human moved it elsewhere themselves, drop it from `tracking` silently — not your concern anymore):

1. Search Gmail for that address, excluding only move.nl's own noreply: `"<address>" -from:no-reply@move.nl after:<requested_at>`

   This deliberately includes Eduard's and Katia's **own** mail. Two different things can confirm a viewing and you must look for both:
   - **the agency writing in** — a separate thread, its own subject, from its own domain, e.g. "Confirmation appointment viewing [ref]"; and
   - **Eduard or Katia telling each other** — they often phone the agency or book online, then mail the other one ("Viewing scheduled on this Friday, 10am"). Nothing from the agency ever arrives in that case, so if you ignore their own mail the viewing never reaches the board. Treat a message from eduryev@gmail.com or katiazoritch@gmail.com stating a booked viewing as a confirmation in its own right.

2. Read whatever thread(s) turn up in full, and read them carefully — this decision is the one that matters most. A **specific date and time that is actually settled** counts as confirmed: the agency saying it's booked, Eduard or Katia explicitly accepting a slot the agency offered, or either of them reporting to the other that they have booked it. An agency's opening message proposing a slot and asking "does this work for you?" is **not** confirmed by itself, even though it has a date and time in it — that's a proposal awaiting a reply. Nor is a list of preferred moments. When genuinely unsure which you're looking at, treat it as **not confirmed**: leave the stage at `applied` and say so in your notification for a human to judge, rather than guess.

3. **Resolving a relative date — do this explicitly, it is where a missed viewing comes from.** Their own notes rarely give a calendar date: "this Friday", "tomorrow", "Monday 10am". Resolve it against the **send date of that message**, not against today, and not against the request date. Work out the weekday of the send date first, then the date you land on, and put the full resolved date in your notification so a human can catch you being wrong — e.g. "sent Sat 19 Sep, 'this Friday' → Fri 25 Sep". If a phrase could plausibly mean two different dates and nothing in the thread settles it, do NOT pick one: leave the card at `applied`, create no calendar event, and ask in your notification.

4. **Every message from an agency here gets forwarded to Katia — see Step B-fwd.** Do NOT forward messages Eduard or Katia sent themselves; they are already both on those.

5. **Confirmed** — take the date and time exactly as settled (translate a Dutch weekday or month for readability; never infer beyond what's written, beyond the relative-date resolution in 3). Where the confirmation came from the agency, use the confirming sender's address; where it came from Eduard's or Katia's own note, use the agency's address from the earlier thread for that listing. Then:
   `python3 src/board_patch.py '{"<listing-id>": {"stage": "scheduled", "viewing_line": "📅 Confirmed: <date>, <time> — <Agency Name> (<agency email>)"}}'`
   Then do **Step C** for that listing, and remove it from `tracking` — resolved for now. Step D keeps watching it from here on.

6. **Proposed, not yet confirmed** — update the note to reflect it, stage stays `applied`: `python3 src/board_patch.py '{"<listing-id>": {"viewing_line": "✉️ Proposed: <date>, <time> — awaiting confirmation — <Agency Name>"}}'`
   Keep it in `tracking`. Do NOT create a calendar event for a proposal (but DO forward it, if it came from the agency).

7. **Nothing new** — leave it, keep it in `tracking`.

Never invent a date, time, or agency email that isn't literally in the email text.

### Step B-fwd — forward the agency's reply to Katia

The agencies only ever write to Eduard, so Katia never sees these unless they're forwarded. Do this for **every** message from an agency in those threads — a proposal, a confirmation, a reschedule, a "sorry, it's sold" — not just the confirmations. Skip anything Eduard or Katia wrote themselves.

Skip any message whose id is already in `forwarded_message_ids`; that list is the only thing stopping an hourly routine from forwarding the same email again and again, so it must be committed in the same push as everything else this run.

    mcp__Gmail__forward
      messageId: <the agency message's id>
      to:  ["katiazoritch@gmail.com"]
      cc:  ["eduryev@gmail.com"]
      forwardText: one plain sentence of context — address, what the agency said,
                   and the date and time if there is one. No invented detail.

Then add the message id to `forwarded_message_ids`.

Afterwards mark both as read, so neither the agency's mail nor Eduard's own cc'd copy sits bold in his inbox:

    mcp__Gmail__update_message_labels  messageId: <agency message id>,        removeLabelIds: ["UNREAD"]
    mcp__Gmail__update_message_labels  messageId: <id returned by forward>,   removeLabelIds: ["UNREAD"]

**This may fail with "Insufficient scope … gmail.modify".** The connector can send mail but was not granted permission to change labels. That is expected and is NOT a failure of the run: the forward has already gone out, which is the part that matters. Carry on normally, don't retry it, don't `--fail` the heartbeat over it, and mention once in your notification that marking-as-read needs Gmail reconnected with modify permission. If it succeeds, say nothing about it.

## Step C — put the confirmed viewing in Google Calendar

Only for a viewing you just confirmed in Step B.5, or a new appointment Step D found. Eduard and Katia go to these together, so the event carries everything they'd want on their phone at the door.

**Do not create a duplicate.** Two guards, both required:
- If `calendar_events` already has this listing id, the event exists — skip, unless the confirmed start time differs from the stored `start`, which is a reschedule: handle it through Step D, never by creating a second event.
- Otherwise search first (`mcp__Google_Calendar__search_events` for `Apt Viewing <address>`). If a matching event is already there, record its id in `calendar_events` and don't create another.

If you have no Google Calendar tools, skip this step, still do everything else, and say in your notification that the event could not be created because the Calendar connector isn't attached.

Create it with `mcp__Google_Calendar__create_event`:

- **summary**: `Apt Viewing: <address>` — exactly this shape, e.g. `Apt Viewing: Achillesstraat 109 H`
- **startTime** / **endTime**: the confirmed date and time, `timeZone` `Europe/Amsterdam`. Viewings here run **15 minutes** — use that whenever only a start time is given, which is the normal case. Only when the email actually states an end time or a duration, use what it says instead.
- **location**: `<address>, <postcode> Amsterdam`, taking the postcode from `data/listings.json`
- **attendees**: `[{"email": "katiazoritch@gmail.com"}]` — Eduard is the organiser automatically
- **description**, in this order, with the listing link FIRST:

      <a href="<listing url from data/listings.json>">View the listing on move.nl</a><br><br>
      <b>Address:</b> <address>, <postcode> Amsterdam<br>
      <b>Agency:</b> <agency name><br>
      <b>Contact:</b> <person who signed the email><br>
      <b>Phone:</b> <phone><br>
      <b>Email:</b> <agency email><br><br>
      <price> · <m2> m² · <rooms> rooms / <bedrooms> bedrooms · Energy <class><br>

  Take the contact person, phone and email from the agency's own mail for that listing — usually in the signature or footer block (e.g. "Telefoonnummer: 020-6471990"). When the confirmation came from Eduard's or Katia's note instead, the agency's details are still in the earlier thread for that address; use those. **Never invent a phone number or a contact name**: if one genuinely isn't there, leave that line out entirely rather than guessing or writing a placeholder. Price/m²/rooms/energy come from `data/listings.json`; drop that line if the listing isn't there.

Then record it: `calendar_events[<listing-id>] = {"event_id": "<id from the response>", "start": "<ISO start you used>", "summary": "Apt Viewing: <address>"}`.

Note: the account adds a Google Meet link to new events automatically and the API won't remove it. Ignore it — it's harmless on an in-person viewing, and not worth a second call.

## Step D — a scheduled viewing is not finished business

**This step exists because two confirmed appointments were moved by email and the calendar kept showing the old times for days.** Both were caught by hand, not by this routine, because Step B drops a listing from `tracking` the moment it is confirmed and nothing looked at it again. Booking a viewing is the *start* of a conversation, not the end of one: slots get moved, cancelled and rebooked, and a second viewing gets arranged after a good first one.

So on **every run**, take each entry in `calendar_events` whose stored `start` is **in the future, or less than 3 days in the past** (a viewing moved on the day is the common case; older than that, let it go), and check whether the email still agrees with it. Do this regardless of the card's stage — `scheduled` and `visited` both qualify, and a `visited` card is exactly where a repeat viewing shows up.

1. Search `"<address>" -from:no-reply@move.nl` for mail **newer than the last time you checked** — practically, `after:` the day before the stored `start` was last written, or just the last 10 days, whichever is wider. Again, this includes Eduard's and Katia's own mail: one of these two misses was renegotiated entirely between Eduard and the agent in a plain thread, the other through the agency's booking system (housapp: "Your appointment on 25-09-2026 at 10:50 is confirmed", "rescheduled to").
2. Read the newest messages in full and work out what the settled time is **now**, using the same bar as Step B.2 (actually settled, not proposed) and the same relative-date rule as Step B.3. Watch for: an agency offering a different slot and Eduard accepting it; either of them asking to shift the time and the agent agreeing; a booking-system confirmation with a new date; a cancellation (Katia mailing "I'm sick, we can't come today"); and a formal confirmation that arrives *after* the informal agreement and restates the time — that last one is the easiest to skim past, because by then you already think you know the answer.
3. Compare it with the stored `start`. Same → nothing to do, don't touch anything, don't mention it. Different → act on which of these it is:

   - **Moved** (the same viewing, a new time). Update the event in place — never create a second one:
     `mcp__Google_Calendar__update_event` with the stored `event_id`, new `startTime`/`endTime` (15 minutes again unless stated), `timeZone: Europe/Amsterdam`. Then set `calendar_events[<id>]["start"]` to the new ISO start, and update the board note:
     `python3 src/board_patch.py '{"<listing-id>": {"viewing_line": "📅 Confirmed: <new date>, <new time> — <Agency Name> (<agency email>) — rescheduled from <old date>"}}'`
     Do **not** change the stage: a card a human moved to `visited` or `disliked` stays where they put it.
   - **A separate, later viewing** of a listing that has already been seen (the card is at `visited`, or the stored `start` is in the past and this new appointment is a fresh one rather than a correction). Here the old event is a record of something that actually happened, so leave it alone: create a **new** event via Step C, then set `calendar_events[<id>]` to the new event, moving the previous `event_id` into `past_event_ids`. Say in the event description which viewing this is, e.g. `<b>Second viewing</b> (Eduard) — Katia saw it on 22 Sep.`
   - **Cancelled with no replacement.** Delete the event (`mcp__Google_Calendar__delete_event`), drop the entry from `calendar_events`, and move the card back:
     `python3 src/board_patch.py '{"<listing-id>": {"stage": "applied", "viewing_line": "✉️ Viewing cancelled <date> — <reason in a few words> — <Agency Name>"}}'`
     Put it back in `tracking` so Step B picks up the rebooking. Again, don't move a card a human has since put in `visited`, `disliked` or `archived`.

4. Forward any agency message you read here that isn't already in `forwarded_message_ids`, exactly as in Step B-fwd. A reschedule is precisely the kind of mail Katia needs to see.
5. Say all of it in your notification, with the old time and the new one, and flag when the new time collides with, or leaves under 30 minutes' travel from, another `Apt Viewing` event that day — three viewings in an hour has already happened and is worth pointing out rather than leaving them to discover at the door.

If a change is real but you cannot pin down the new time (the thread trails off, two dates are equally plausible), change nothing, leave the event where it is, and ask in your notification. An event that is wrong in a way you flagged is recoverable; one you silently moved to the wrong day is not.

## Finishing

If you read any email this run (new request, tracking check, or Step D), save `data/viewing_tracker_state.json` and commit and push to `main` (plain git is fine here — this file isn't touched by anyone else, unlike board.json) — even when the outcome was "nothing to move." Only skip the commit when there was truly nothing new to look at at all. `calendar_events` and `forwarded_message_ids` must be committed in the same push as the actions that created them — if they aren't persisted, the next run duplicates the event and re-forwards the mail.

Notify whenever you read and processed anything: listings moved to Viewing Applied (address + agency), listings moved to **Viewing Scheduled** (address, the fully resolved date and time, how you resolved it if the source said something like "this Friday", agency, that the calendar invite went to Katia, and that the agency's mail was forwarded to her), **viewings rescheduled, cancelled or booked a second time (old time → new time)**, agency replies forwarded, off-board addresses found, requests found for a listing already disliked/archived/visited, or proposals awaiting confirmation. State plainly when the answer is "found N requests, all already archived, nothing to do" rather than staying quiet. Only stay fully silent when there was nothing new in Gmail at all this run.

## LAST STEP, ALWAYS — no exceptions

Finish every single run, including a fully silent one where Gmail had nothing new, with:

    python3 src/heartbeat.py viewing_tracker "<one-line summary of what happened>"

Add `--fail` before the summary if you could not do your job this run (no Gmail, board_patch.py failing, GitHub unreachable). A refused mark-as-read is NOT such a case. Examples:

    python3 src/heartbeat.py viewing_tracker "no new viewing requests; 2 tracked, 4 scheduled unchanged"
    python3 src/heartbeat.py viewing_tracker "Pythagorasstraat 8 3 confirmed Fri 25 Sep 10:00 from Eduard's own note; invite sent"
    python3 src/heartbeat.py viewing_tracker "Achillesstraat 109 H moved 15 Sep 10:00 → 24 Sep 17:15; event updated"
    python3 src/heartbeat.py viewing_tracker "3 requests found, all already archived — not revived"
    python3 src/heartbeat.py viewing_tracker --fail "board_patch.py could not push after 4 retries"

This writes `health.json` on the `board` branch (it is the ONLY file on that branch you may write outside `board_patch.py`), and the board's header reads it to show Eduard that you are still alive and what you last did. It is NOT a substitute for the notification rules above — it is in addition to them, and it runs even on the runs where you correctly notify nothing at all.

Skipping it makes the live board display a red warning as though the routine had died, so run it even when Gmail was completely empty this hour. If the heartbeat command itself errors, say so in your notification.
