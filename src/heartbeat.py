#!/usr/bin/env python3
"""Record that a routine actually ran, in health.json on the `board` branch.

    python3 src/heartbeat.py listing_refresh "no new digests; 157 listings"
    python3 src/heartbeat.py viewing_tracker "2 requests found, both archived"
    python3 src/heartbeat.py listing_refresh --fail "move.nl unreachable"

A routine that finds nothing to do otherwise leaves no trace, so a broken
routine and an idle one look identical from the outside — that ambiguity cost
a full day of debugging once. Every run writes here regardless of outcome, and
the board shows the timestamps, so "is the robot still alive" is answered by
looking rather than by trusting a green status.

Lives on `board`, not `main`: heartbeats must not trigger a Pages rebuild, and
the page already polls that branch.
"""
import json, subprocess, sys, os, tempfile, shutil, time, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCH = 'board'
FILE = 'health.json'
KEYS = ('listing_refresh', 'viewing_tracker')

def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f'{cmd} failed:\n{r.stdout}\n{r.stderr}')
    return r

def main():
    args = [a for a in sys.argv[1:]]
    ok = True
    if '--fail' in args:
        ok = False
        args.remove('--fail')
    if len(args) != 2:
        raise SystemExit(f'usage: heartbeat.py <{"|".join(KEYS)}> [--fail] "<one-line summary>"')
    key, summary = args
    if key not in KEYS:
        raise SystemExit(f'unknown routine {key!r}; expected one of {", ".join(KEYS)}')

    entry = {
        'at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'ok': ok,
        'summary': summary[:300],
    }

    run(['git', 'config', 'remote.origin.fetch', '+refs/heads/*:refs/remotes/origin/*'], cwd=ROOT)
    run(['git', 'fetch', 'origin', BRANCH], cwd=ROOT)
    wt = tempfile.mkdtemp(prefix='heartbeat-')
    try:
        run(['git', 'worktree', 'add', '-q', wt, f'origin/{BRANCH}', '--detach'], cwd=ROOT)
        for attempt in range(4):
            run(['git', 'fetch', 'origin', BRANCH], cwd=wt)
            run(['git', 'reset', '-q', '--hard', f'origin/{BRANCH}'], cwd=wt)
            path = os.path.join(wt, FILE)
            health = json.load(open(path)) if os.path.exists(path) else {}
            health[key] = entry
            json.dump(health, open(path, 'w'), indent=1, ensure_ascii=False)
            run(['git', 'add', FILE], cwd=wt)
            commit = subprocess.run(
                ['git', 'commit', '-q', '-m', f'health: {key}',
                 '--author=Routine heartbeat <noreply@anthropic.com>'],
                cwd=wt, capture_output=True, text=True)
            if commit.returncode != 0:
                raise RuntimeError(commit.stdout + commit.stderr)
            push = subprocess.run(['git', 'push', 'origin', f'HEAD:{BRANCH}'],
                                  cwd=wt, capture_output=True, text=True)
            if push.returncode == 0:
                print(f'heartbeat {key}: {entry["at"]} ok={ok} — {summary}')
                return
            print(f'push rejected (attempt {attempt + 1}/4), retrying against latest {BRANCH}...')
            time.sleep(2)
        raise SystemExit('heartbeat: gave up after retries')
    finally:
        run(['git', 'worktree', 'remove', '--force', wt], cwd=ROOT, check=False)
        shutil.rmtree(wt, ignore_errors=True)

if __name__ == '__main__':
    main()
