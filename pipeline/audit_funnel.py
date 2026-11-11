#!/usr/bin/env python3
"""
Funnel audit: estimate what the pre-filter misses.

The review batches only measure the model on the candidates the pre-filter let
through. This script looks at the other side: GKG records of one day that did NOT
pass the pre-filter but carry a housing or land theme, or a settlement or
occupation word in the title, located in the Global South (the "near misses"). It draws a
random sample and writes it as a review batch. The share of reviewers' "yes" in
the sample, times the number of near misses, estimates the relevant stories the
system never sees on such a day.

Run about once a month, on a full day or a sample of its files:
  python pipeline/audit_funnel.py --date 2026-11-10 --every 4 --list-untranslated
  python pipeline/audit_funnel.py --date 2026-11-10 --every 4 --translations tr.json --out <dir>
"""

import argparse
import json
import os
import random
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'prototype'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_map_data import GLOBAL_NORTH  # noqa: E402
from gkg_prototype import SETTLEMENT_WORD_RE, collect, fold, url_text  # noqa: E402

READABLE = {'por', 'spa', 'eng', 'fra'}


def in_global_south(record):
    if not record['locations']:
        return False
    country = fold(record['locations'][0]['name'].split(',')[-1].strip())
    return country not in GLOBAL_NORTH


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    ap.add_argument('--every', type=int, default=4, help='use 1 of every N 15-min files')
    ap.add_argument('--sample', type=int, default=40)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--translations', help='JSON file {original title: Portuguese title}')
    ap.add_argument('--list-untranslated', action='store_true')
    ap.add_argument('--out')
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    _, stats, counters, all_urls = collect(args.date, args.every, near_miss=True)
    # Files arrive in any order; sort so the same seed always draws the same sample
    near, seen_titles = [], set()
    for r in sorted((r for r in counters['near_miss'] if in_global_south(r)), key=lambda r: r['url']):
        key = r['title'].strip().lower()
        if key not in seen_titles:
            seen_titles.add(key)
            near.append(r)
    for r in near:
        r['settlement_word'] = bool(SETTLEMENT_WORD_RE.search(fold(f"{r['title']} {url_text(r['url'])}")))
    # Two strata: a settlement/occupation word in the title (likelier misses) and a
    # housing/land theme only (mostly real-estate news); half the sample from each
    by_word = [r for r in near if r['settlement_word']]
    by_theme = [r for r in near if not r['settlement_word']]
    rng = random.Random(args.seed)
    half = args.sample // 2
    sample = rng.sample(by_word, min(half, len(by_word)))
    sample += rng.sample(by_theme, min(args.sample - len(sample), len(by_theme)))
    rng.shuffle(sample)

    if args.list_untranslated:
        print(json.dumps({r['title']: '' for r in sample if r['language'] not in READABLE}, ensure_ascii=False, indent=1))
        return
    if not args.out:
        sys.exit('--out is required unless --list-untranslated')
    translations = {}
    if args.translations:
        with open(args.translations, encoding='utf-8') as f:
            translations = json.load(f)

    batch = f'funil-{args.date}'
    os.makedirs(args.out, exist_ok=True)
    for order, r in enumerate(sample, 1):
        settlement_word = r['settlement_word']
        doc = {
            'batch': batch, 'order': order, 'kind': 'funnel', 'story_id': f'{batch}-{order:03d}',
            'title': r['title'], 'title_pt': translations.get(r['title']) or None,
            'url': r['url'], 'source': r['source'], 'language': r['language'], 'records': 1, 'other_titles': [],
            'removal_terms': [], 'signal': {'themes': r['themes'], 'settlement_word': settlement_word},
            'model': {'relevant': None, 'topics': [], 'removal': None, 'reason': ''},
        }
        with open(os.path.join(args.out, f'{batch}_{order:03d}.json'), 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False)

    batch_doc = {
        'name': f'Funil {args.date}', 'days': [args.date], 'items': len(sample), 'kind': 'funnel',
        'counts': {'funnel': len(sample)},
        # Near misses in the files read, and scaled to the whole day
        'near_miss_in_files': len(near), 'near_miss_per_day_estimate': len(near) * args.every,
        'strata_in_files': {'settlement_word': len(by_word), 'theme_only': len(by_theme)},
        'strata_in_sample': {'settlement_word': sum(r['settlement_word'] for r in sample),
                             'theme_only': sum(not r['settlement_word'] for r in sample)},
        'files_read': stats['files_ok'], 'every': args.every, 'records_seen': len(all_urls),
    }
    with open(os.path.join(args.out, '_batch.json'), 'w', encoding='utf-8') as f:
        json.dump(batch_doc, f, ensure_ascii=False)
    print(json.dumps(batch_doc, ensure_ascii=False))
    print(f"{len(sample)} item files in {args.out}")


if __name__ == '__main__':
    main()
