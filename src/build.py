#!/usr/bin/env python3
"""Build docs/index.html: the AVT house-hunt board with its listing data inlined.

    python3 src/build.py

Re-run after parse_emails.py picks up new AVT digests.
"""
import json, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUTOFF = '2026-09-10'          # anything first seen before this lands in Archived
MIN_M2 = 70                    # below this, or with one bedroom, it isn't worth a look
MIN_BEDROOMS = 2

def too_small(r):
    """Whether a listing starts in Archived on size alone.

    An unknown bedroom count is NOT a reason to hide a flat — that would bury
    listings we merely failed to parse, which is the opposite of useful."""
    if r['m2'] < MIN_M2:
        return True
    beds = r.get('bedrooms')
    return beds is not None and beds < MIN_BEDROOMS

def main():
    listings = json.load(open(f'{ROOT}/data/listings.json'))
    pc4 = json.load(open(f'{ROOT}/data/pc4.json'))

    slim = []
    for r in listings:
        slim.append({
            'id': r['id'],
            'address': r['address'],
            'postcode': r['postcode'],
            'url': r['url'],
            'image': r.get('image'),
            'price': r['price'],
            'm2': r['m2'],
            'rooms': r['rooms'],
            'bedrooms': r.get('bedrooms'),
            'type': r.get('type'),
            'first_seen': r['first_seen'],
            'energy': r.get('energy'),
            'garden': r.get('garden'),
            'terrace': r.get('terrace'),
            'garden_size': r.get('garden_size'),
            'status': r.get('status'),
            'tenure': r.get('tenure'),
            'enriched': r.get('enriched'),
            'listed': r.get('listed'),
            'erfpacht_until': r.get('erfpacht_until'),
            # only the DEFAULT: a card either of them has moved keeps its own
            # stage from board.json, so a small flat they liked anyway stays liked
            'defaultStage': 'backlog' if r['first_seen'] >= CUTOFF and not too_small(r) else 'archived',
        })
    slim.sort(key=lambda r: (r['first_seen'], r['address']))

    # The listing catalogue is baked into the page, so a tab left open never
    # learns about listings added since it loaded — and a card the viewing
    # tracker moves for one of them stays invisible, because the board sync
    # skips ids the page doesn't know. version.json lets an open board notice
    # it has gone stale and offer a reload.
    build_id = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}/{len(slim)}"

    tpl = open(f'{ROOT}/src/template.html').read()
    html = (tpl
            .replace('__LISTINGS__', json.dumps(slim, ensure_ascii=False, separators=(',', ':')))
            .replace('__PC4__', json.dumps(pc4, ensure_ascii=False, separators=(',', ':')))
            .replace('__BUILT__', datetime.date.today().isoformat())
            .replace('__BUILD_ID__', build_id)
            .replace('__CUTOFF__', CUTOFF)
            .replace('__MIN_M2__', str(MIN_M2)))

    os.makedirs(f'{ROOT}/docs', exist_ok=True)
    out = f'{ROOT}/docs/index.html'
    open(out, 'w').write(html)
    json.dump({'build': build_id, 'listings': len(slim)},
              open(f'{ROOT}/docs/version.json', 'w'), indent=1)

    live = sum(1 for r in slim if r['defaultStage'] != 'archived')
    withE = sum(1 for r in slim if r.get('energy'))
    print(f'{out}: {len(slim)} listings ({live} backlog / {len(slim)-live} archived), '
          f'{withE} with energy class, {os.path.getsize(out)//1024} KB')

if __name__ == '__main__':
    main()
