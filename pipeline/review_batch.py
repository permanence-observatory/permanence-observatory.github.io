#!/usr/bin/env python3
"""
Build a review batch from one or more daily history files.

One item per story (repeated reprints count once):
  - every story the model marked relevant or as a removal,
  - every story flagged by the removal rule, and every story with a removal word
    even if discarded (removals are rare, so all of them are checked),
  - a random sample of stories the model discarded (to estimate what it misses),
  - pairs of articles to check the story grouping (--pairs): half joined in one story
    by the collector, half kept apart although the model read the same place.
Items are shuffled and carry the model's answer, which the review page shows
only after the reviewer answers. Writes one JSON file per item plus the batch
document into --out, ready to load into the review page's database.

Usage:
  python pipeline/review_batch.py data/gkg/2026/11/2026-11-05.jsonl --out <dir>
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_day import AMBIGUOUS_NAMES, assign_stories, removal_check  # noqa: E402

READABLE = {'por', 'spa', 'eng', 'fra'}  # languages the team reads; others get a translation


def load(path):
    with open(path, encoding='utf-8') as f:
        records = [json.loads(line) for line in f]
    day = os.path.basename(path)[:10]
    if records and 'story_id' not in records[0]:
        # Files written before story grouping and the stricter removal rule
        for r in records:
            if r.get('review') and r['relevant'] == 'uncertain':
                r['relevant'] = 'no'
            r['removal_terms'], flag = removal_check(r, AMBIGUOUS_NAMES)
            r['review'] = flag and r['relevant'] in ('no', None)
            if r['review'] and r['relevant'] == 'no':
                r['relevant'] = 'uncertain'
        assign_stories(records, day)
    for r in records:
        # Files classified before topics and the removal question
        r.setdefault('topics', [])
        r.setdefault('removal', None)
    return records


def grouping_pairs(stories, n, rng):
    """Article pairs for checking the story grouping, as (type, record_a, record_b):
    'joined' = two different titles the collector put in one story (stories on the map
    first); 'separated' = two
    relevant articles of the same day in different stories whose model-read place is the
    same (the likeliest missed merges). Half of each when possible."""
    if n <= 0:
        return []
    joined, joined_other = [], []
    for sid in sorted(stories):
        g = [r for r in stories[sid] if r['title']]
        titles = {}
        for r in g:
            titles.setdefault(r['title'].strip().lower(), r)
        if len(titles) >= 2:
            a, b = rng.sample(sorted(titles.values(), key=lambda r: r['url']), 2)
            # Stories on the map first; others only fill the quota
            counts = any(r['relevant'] == 'yes' or r['removal'] for r in g)
            (joined if counts else joined_other).append(('joined', a, b))
    by_place = {}
    for sid in sorted(stories):
        for r in stories[sid]:
            if r['title'] and (r['relevant'] == 'yes' or r['removal']) and r.get('place'):
                by_place.setdefault((sid[:10], r['place'].strip().lower()), {}).setdefault(sid, r)
    separated = []
    for key in sorted(by_place):
        faces = sorted(by_place[key].values(), key=lambda r: r['story_id'])
        for i in range(len(faces)):
            for j in range(i + 1, len(faces)):
                separated.append(('separated', faces[i], faces[j]))
    half = n // 2
    take_j = min(len(joined) + len(joined_other), max(half, n - len(separated)))
    take_s = min(len(separated), n - take_j)
    first = rng.sample(joined, min(take_j, len(joined)))
    rest = rng.sample(joined_other, take_j - len(first))
    return first + rest + rng.sample(separated, take_s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--batch', help='batch name (default: the day, or first~last)')
    ap.add_argument('--sample', type=int, default=20, help='discarded stories to sample')
    ap.add_argument('--relevant-sample', type=int, default=20,
                    help='relevant (non-removal) stories to sample; 0 = all. Removal and flagged stories are always all')
    ap.add_argument('--pairs', type=int, default=10,
                    help='article pairs to check the story grouping (half joined, half kept apart); 0 = none')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--translations', help='JSON file {original title: Portuguese title} shown to reviewers')
    ap.add_argument('--list-untranslated', action='store_true',
                    help='print the titles in languages other than por/spa/eng/fra and stop')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    records = [r for p in sorted(args.files) for r in load(p)]
    days = sorted({os.path.basename(p)[:10] for p in args.files})
    batch = args.batch or (days[0] if len(days) == 1 else f'{days[0]}~{days[-1]}')

    stories = {}
    for r in records:
        stories.setdefault(r['story_id'], []).append(r)

    def kind(group):
        if any(r['removal'] for r in group):
            return 'removal'
        if any(r['review'] for r in group):
            return 'flagged'
        if any(r['relevant'] == 'yes' for r in group):
            return 'relevant'
        if any(r.get('removal_terms') for r in group):
            return 'removal_terms'
        if all(r['relevant'] == 'no' for r in group):
            return 'discarded'
        return 'other'

    by_kind = {}
    for sid, g in stories.items():
        by_kind.setdefault(kind(g), []).append(sid)
    rng = random.Random(args.seed)
    discarded = sorted(by_kind.get('discarded', []))
    relevant = sorted(by_kind.get('relevant', []))
    if args.relevant_sample and len(relevant) > args.relevant_sample:
        relevant = rng.sample(relevant, args.relevant_sample)
    picked = [(s, k) for k in ('removal', 'flagged', 'removal_terms') for s in by_kind.get(k, [])]
    picked += [(s, 'relevant') for s in relevant]
    picked += [(s, 'sample') for s in rng.sample(discarded, min(args.sample, len(discarded)))]
    picked += [(p, 'pair') for p in grouping_pairs(stories, args.pairs, rng)]
    rng.shuffle(picked)

    def face_of(group):
        # Show the relevant record (or the flagged one, or the first) as the story's face
        for test in (lambda r: r['removal'], lambda r: r['review'], lambda r: r['relevant'] == 'yes',
                     lambda r: r.get('removal_terms')):
            hit = next((r for r in group if test(r)), None)
            if hit:
                return hit
        return group[0]

    def shown_records(sid, k):
        return list(sid[1:]) if k == 'pair' else [face_of(stories[sid])]

    if args.list_untranslated:
        titles = sorted({r['title'] for s, k in picked for r in shown_records(s, k)
                         if r['language'] not in READABLE and r['title']})
        print(json.dumps({t: '' for t in titles}, ensure_ascii=False, indent=1))
        return
    translations = {}
    if args.translations:
        with open(args.translations, encoding='utf-8') as f:
            translations = json.load(f)

    os.makedirs(args.out, exist_ok=True)
    manifest = []
    for order, (sid, k) in enumerate(picked, 1):
        doc_id = f"{batch}~{order:03d}".replace('~', '_')
        if k == 'pair':
            pair_type, ra, rb = sid
            side = lambda r: {'title': r['title'] or '(sem título)', 'title_pt': translations.get(r['title']) or None,  # noqa: E731
                              'url': r['url'], 'source': r['source'], 'language': r['language']}
            doc = {'batch': batch, 'order': order, 'kind': 'pair', 'pair_type': pair_type,
                   'story_ids': [ra['story_id'], rb['story_id']], 'a': side(ra), 'b': side(rb),
                   'title': ra['title'], 'url': ra['url'],
                   'model': {'same_story': ra['story_id'] == rb['story_id']}}
            with open(os.path.join(args.out, f'{doc_id}.json'), 'w', encoding='utf-8') as f:
                json.dump(doc, f, ensure_ascii=False)
            manifest.append(doc_id)
            continue
        g = stories[sid]
        face = face_of(g)
        others = []
        for r in g:
            if r['title'] and r['title'] != face['title'] and r['title'] not in others:
                others.append(r['title'])
        doc = {
            'batch': batch, 'order': order, 'kind': k, 'story_id': sid,
            'title': face['title'] or '(sem título)', 'title_pt': translations.get(face['title']) or None,
            'url': face['url'], 'source': face['source'],
            'language': face['language'], 'records': len(g), 'other_titles': others[:3],
            'removal_terms': face.get('removal_terms', []),
            'model': {'relevant': face['relevant'], 'topics': face['topics'], 'removal': face['removal'],
                      'event_type': face.get('event_type'), 'reason': face.get('reason') or ''},
        }
        with open(os.path.join(args.out, f'{doc_id}.json'), 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False)
        manifest.append(doc_id)

    counts = {k: sum(1 for _, kk in picked if kk == k)
              for k in ('removal', 'flagged', 'relevant', 'removal_terms', 'sample', 'pair')}
    # Population sizes, so sampled rates can be scaled back to the whole day
    batch_doc = {'name': batch, 'days': days, 'items': len(picked), 'counts': counts,
                 'candidates': len(records), 'stories': len(stories),
                 'relevant_stories': len(by_kind.get('relevant', [])),
                 'discarded_stories': len(discarded)}
    with open(os.path.join(args.out, '_batch.json'), 'w', encoding='utf-8') as f:
        json.dump(batch_doc, f, ensure_ascii=False)
    print(json.dumps(batch_doc, ensure_ascii=False))
    print(f"{len(manifest)} item files in {args.out}")


if __name__ == '__main__':
    main()
