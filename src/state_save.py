#!/usr/bin/env python3
"""Merge data/viewing_tracker_state.json back onto main and push, race-safely.

    python3 src/state_save.py                      # push the working copy
    python3 src/state_save.py path/to/state.json   # or an explicit file

A plain commit was fine while the viewing tracker was the only writer and
nothing else pushed to main during its run. Neither holds reliably: the
listing-refresh routine pushes too, a second house-hunt routine can be
re-enabled, and staggered copies of the tracker are a supported setup. A
rejected push would throw away that run's record of forwards it already sent
and events it already created, which is exactly how a forward gets sent twice.

So: re-read the branch's head, merge, commit, retry. The merge is a union, not
a last-writer-wins, because every field here records something that HAS already
happened out in the world:

  processed_request_ids / forwarded_message_ids  union, order preserved
  calendar_events                                per listing, newest `start` wins
  tracking                                       per listing; a delete beats an
                                                 add, since dropping a listing
                                                 means it was resolved
"""
import json, subprocess, sys, os, tempfile, shutil, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCH = 'main'
FILE = 'data/viewing_tracker_state.json'
LISTS = ('processed_request_ids', 'forwarded_message_ids')

def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f'{cmd} failed:\n{r.stdout}\n{r.stderr}')
    return r

def union(a, b):
    """b's new entries appended to a, keeping order and dropping repeats."""
    seen, out = set(), []
    for x in list(a) + list(b):
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def merge(theirs, mine, base):
    out = dict(theirs)
    for k in LISTS:
        out[k] = union(theirs.get(k, []), mine.get(k, []))

    # An event both runs touched: keep whichever start is later, since a
    # reschedule only ever moves an appointment forward in wall-clock terms
    # within one hour of each other. Carry past_event_ids across either way.
    cal = dict(theirs.get('calendar_events', {}))
    for lid, ev in mine.get('calendar_events', {}).items():
        cur = cal.get(lid)
        if cur is None or str(ev.get('start', '')) > str(cur.get('start', '')):
            merged = dict(ev)
            merged['past_event_ids'] = union(cur.get('past_event_ids', []) if cur else [],
                                             ev.get('past_event_ids', []))
            if not merged['past_event_ids']:
                merged.pop('past_event_ids')
            cal[lid] = merged
    out['calendar_events'] = cal

    # tracking is a to-do list, so a removal is a real decision: if this run
    # dropped a listing it had in `base`, honour that over the other run
    # re-adding it. Otherwise take the union.
    tr = dict(theirs.get('tracking', {}))
    tr.update(mine.get('tracking', {}))
    for lid in base.get('tracking', {}):
        if lid not in mine.get('tracking', {}):
            tr.pop(lid, None)
    out['tracking'] = tr
    return out

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, FILE)
    mine = json.load(open(src))
    base = json.loads(run(['git', 'show', f'origin/{BRANCH}:{FILE}'], cwd=ROOT).stdout or '{}')

    run(['git', 'config', 'remote.origin.fetch', '+refs/heads/*:refs/remotes/origin/*'], cwd=ROOT)
    wt = tempfile.mkdtemp(prefix='state-')
    try:
        run(['git', 'fetch', 'origin', BRANCH], cwd=ROOT)
        run(['git', 'worktree', 'add', '-q', wt, f'origin/{BRANCH}', '--detach'], cwd=ROOT)
        for attempt in range(4):
            run(['git', 'fetch', 'origin', BRANCH], cwd=wt)
            run(['git', 'reset', '-q', '--hard', f'origin/{BRANCH}'], cwd=wt)
            path = os.path.join(wt, FILE)
            theirs = json.load(open(path)) if os.path.exists(path) else {}
            out = merge(theirs, mine, base)
            json.dump(out, open(path, 'w'), indent=1, ensure_ascii=False)
            open(path, 'a').write('\n')
            run(['git', 'add', FILE], cwd=wt)
            if not subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=wt).returncode:
                print('state_save: nothing changed')
                return
            run(['git', 'commit', '-q', '-m', 'viewing tracker: update state',
                 '--author=Viewing tracker <noreply@anthropic.com>'], cwd=wt)
            if subprocess.run(['git', 'push', 'origin', f'HEAD:{BRANCH}'],
                              cwd=wt, capture_output=True, text=True).returncode == 0:
                n = len(out.get('forwarded_message_ids', []))
                print(f'state_save: pushed ({n} forwarded ids, '
                      f'{len(out.get("tracking", {}))} tracked, '
                      f'{len(out.get("calendar_events", {}))} events)')
                return
            print(f'push rejected (attempt {attempt + 1}/4), remerging against latest {BRANCH}...')
            time.sleep(2)
        raise SystemExit('state_save: gave up after retries')
    finally:
        run(['git', 'worktree', 'remove', '--force', wt], cwd=ROOT, check=False)
        shutil.rmtree(wt, ignore_errors=True)

if __name__ == '__main__':
    main()
