#!/usr/bin/env python3
"""Safely merge a patch into the shared board (board.json on the `board`
branch) without clobbering concurrent writes from the live page — every open
board polls and commits to that file every ~10s.

    python3 src/board_patch.py '{"<listing-id>": {"stage": "applied", "viewing_line": "..."}}'

Each key is a listing id. Fields merge shallowly into that listing's existing
entry, same as the page's own patch(), and `ts` is set to write time so the
page's per-listing last-writer-wins merge treats it correctly.

`viewing_line`, if given, is not stored directly: it becomes the FIRST line of
`note`, replacing any previous machine-written first line (one starting with
"✉️ " or "📅 ") while preserving everything else a human typed into notes.
Never touches `note` when no `viewing_line` is given.

Retries a few times against the branch's current HEAD if the push races a
browser's own write.
"""
import json, subprocess, sys, os, tempfile, shutil, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCH = 'board'
FILE = 'board.json'
MACHINE_PREFIXES = ('✉️ ', '📅 ')

def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f'{cmd} failed:\n{r.stdout}\n{r.stderr}')
    return r

def merge_note(existing_note, viewing_line):
    lines = (existing_note or '').split('\n')
    kept = [ln for ln in lines if not ln.startswith(MACHINE_PREFIXES)]
    return '\n'.join([viewing_line] + kept).strip()

def apply_patch(state, patch):
    state.setdefault('items', {})
    now = int(time.time() * 1000)
    for listing_id, fields in patch.items():
        fields = dict(fields)
        cur = dict(state['items'].get(listing_id, {}))
        line = fields.pop('viewing_line', None)
        if line is not None:
            fields['note'] = merge_note(cur.get('note'), line)
        cur.update(fields)
        cur['ts'] = now
        state['items'][listing_id] = cur
    return state

def main():
    patch = json.loads(sys.argv[1])
    # this repo's clone may have no fetch refspec configured at all (seen in
    # practice — a fresh session clone can leave remote.origin.fetch unset,
    # in which case `git fetch origin <branch>` never creates an
    # `origin/<branch>` ref to check out). Set it unconditionally; it's a
    # no-op if already correct.
    run(['git', 'config', 'remote.origin.fetch', '+refs/heads/*:refs/remotes/origin/*'], cwd=ROOT)
    run(['git', 'fetch', 'origin', BRANCH], cwd=ROOT)
    wt = tempfile.mkdtemp(prefix='board-patch-')
    try:
        run(['git', 'worktree', 'add', '-q', wt, f'origin/{BRANCH}', '--detach'], cwd=ROOT)
        for attempt in range(4):
            run(['git', 'fetch', 'origin', BRANCH], cwd=wt)
            run(['git', 'reset', '-q', '--hard', f'origin/{BRANCH}'], cwd=wt)
            path = os.path.join(wt, FILE)
            state = json.load(open(path)) if os.path.exists(path) else {'items': {}}
            state = apply_patch(state, patch)
            json.dump(state, open(path, 'w'), indent=1, ensure_ascii=False)
            run(['git', 'add', FILE], cwd=wt)
            commit = subprocess.run(
                ['git', 'commit', '-q', '-m', 'board: ' + ', '.join(patch.keys()),
                 '--author=Viewing tracker <noreply@anthropic.com>'],
                cwd=wt, capture_output=True, text=True)
            if commit.returncode != 0:
                if 'nothing to commit' in (commit.stdout + commit.stderr):
                    print('nothing to commit (patch already applied)')
                    return
                raise RuntimeError(commit.stdout + commit.stderr)
            push = subprocess.run(['git', 'push', 'origin', f'HEAD:{BRANCH}'],
                                   cwd=wt, capture_output=True, text=True)
            if push.returncode == 0:
                print('patched:', ', '.join(patch.keys()))
                return
            print(f'push rejected (attempt {attempt + 1}/4), retrying against latest {BRANCH}...')
            time.sleep(2)
        raise SystemExit('board_patch: gave up after retries — a browser is writing very fast, try again')
    finally:
        run(['git', 'worktree', 'remove', '--force', wt], cwd=ROOT, check=False)
        shutil.rmtree(wt, ignore_errors=True)

if __name__ == '__main__':
    main()
