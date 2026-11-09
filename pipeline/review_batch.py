#!/usr/bin/env python3
"""
Build a review batch from one or more daily history files.

One item per story (repeated reprints count once):
  - every story the model marked relevant,
  - every story flagged by the removal rule,
  - a random sample of stories the model discarded (to estimate what it misses).
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
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--batch', help='batch name (default: the day, or first~last)')
    ap.add_argument('--sample', type=int, default=20, help='discarded stories to sample')
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
        if any(r['relevant'] == 'yes' for r in group):
            return 'relevant'
        if any(r['review'] for r in group):
            return 'flagged'
        if all(r['relevant'] == 'no' for r in group):
            return 'discarded'
        return 'other'

    by_kind = {}
    for sid, g in stories.items():
        by_kind.setdefault(kind(g), []).append(sid)
    rng = random.Random(args.seed)
    discarded = sorted(by_kind.get('discarded', []))
    picked = ([(s, 'relevant') for s in by_kind.get('relevant', [])]
              + [(s, 'flagged') for s in by_kind.get('flagged', [])]
              + [(s, 'sample') for s in rng.sample(discarded, min(args.sample, len(discarded)))])
    rng.shuffle(picked)

    def face_of(group):
        # Show the relevant record (or the flagged one, or the first) as the story's face
        return next((r for r in group if r['relevant'] == 'yes'), next((r for r in group if r['review']), group[0]))

    if args.list_untranslated:
        titles = sorted({face_of(stories[s])['title'] for s, _ in picked
                         if face_of(stories[s])['language'] not in READABLE and face_of(stories[s])['title']})
        print(json.dumps({t: '' for t in titles}, ensure_ascii=False, indent=1))
        return
    translations = {}
    if args.translations:
        with open(args.translations, encoding='utf-8') as f:
            translations = json.load(f)

    os.makedirs(args.out, exist_ok=True)
    manifest = []
    for order, (sid, k) in enumerate(picked, 1):
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
            'model': {'relevant': face['relevant'], 'event_type': face['event_type'],
                      'reason': face.get('reason') or ''},
        }
        doc_id = f"{batch}~{order:03d}".replace('~', '_')
        with open(os.path.join(args.out, f'{doc_id}.json'), 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False)
        manifest.append(doc_id)

    counts = {k: sum(1 for _, kk in picked if kk == k) for k in ('relevant', 'flagged', 'sample')}
    batch_doc = {'name': batch, 'days': days, 'items': len(picked), 'counts': counts,
                 'candidates': len(records), 'stories': len(stories),
                 'discarded_stories': len(discarded)}
    with open(os.path.join(args.out, '_batch.json'), 'w', encoding='utf-8') as f:
        json.dump(batch_doc, f, ensure_ascii=False)
    print(json.dumps(batch_doc, ensure_ascii=False))
    print(f"{len(manifest)} item files in {args.out}")


if __name__ == '__main__':
    main()
