#!/usr/bin/env python3
"""
Daily collector: GDELT GKG raw files -> pre-filter -> language model -> daily history file.

Runs alongside the current map (gdelt_version_v21.py) without touching it. For one
UTC day it:
  1. downloads the 96 GKG files (English + translated feeds) and keeps candidates
     that match the SLUMS theme, a settlement name (checked against the GKG
     locations) or a keyword  -- same filter as prototype/gkg_prototype.py;
  2. classifies each unique title with a local open model served by Ollama
     (relevance + event type), using the prompt in prototype/classify_llm.py;
  3. never lets a removal story be dropped silently: if the title or URL has a
     removal word (eviction, desalojo, despejo, déguerpissement...) and the model
     says "no", the record becomes "uncertain" and is flagged for review;
  4. writes every candidate, relevant or not, to data/gkg/YYYY/MM/YYYY-MM-DD.jsonl,
     with the model name and prompt version, so the history can be re-checked or
     re-classified later.

Usage:
  python pipeline/collect_day.py --date 2026-11-05
  python pipeline/collect_day.py --date 2026-11-05 --every 32 --no-llm   # quick plumbing test
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'prototype'))
from classify_llm import (DEFAULT_ENDPOINT, EVENT_TYPES, PROMPT_VERSION,  # noqa: E402
                          call_model)
from gkg_prototype import collect, fold, url_text  # noqa: E402

PIPELINE_VERSION = '2026-11-06.1'

# Removal words, matched on accent-free lowercase title + URL words
REMOVAL_RE = re.compile(
    r'\b(evict\w*|demoli\w*|bulldoz\w*|razed|desaloj\w*|desmantel\w*|despej\w*|'
    r'remoc\w*|reintegracao de posse|deguerpi\w*|demantel\w*)\b')


def removal_terms(record):
    return sorted(set(REMOVAL_RE.findall(fold(f"{record['title']} {url_text(record['url'])}"))))


def classify(records, model, endpoint, batch):
    """Classify unique titles; records sharing a title share the answer."""
    by_title = {}
    for r in records:
        key = (r['title'] or r['url']).strip().lower()
        by_title.setdefault(key, []).append(r)
    unique = list(by_title.values())
    print(f"Classifying {len(unique)} unique titles ({len(records)} records) with {model}", flush=True)
    t0 = time.perf_counter()
    for i in range(0, len(unique), batch):
        group = unique[i:i + batch]
        items = [{'id': str(j), 'title': g[0]['title'] or '(no title)', 'url': g[0]['url'],
                  'language': g[0]['language'],
                  'gdelt_locations': '; '.join(l['name'] for l in g[0]['locations'][:3])}
                 for j, g in enumerate(group)]
        try:
            answers, _ = call_model(endpoint, model, items)
        except RuntimeError as e:
            print(f"   batch {i // batch}: {e}; marking as unclassified", flush=True)
            answers = []
        by_id = {str(a.get('id')): a for a in answers if isinstance(a, dict)}
        for j, g in enumerate(group):
            a = by_id.get(str(j)) or (answers[j] if len(answers) == len(group) and isinstance(answers[j], dict) else None)
            for r in g:
                if a is None:
                    r.update(relevant=None, event_type=None, reason=None)
                else:
                    r.update(relevant=a.get('relevant') if a.get('relevant') in ('yes', 'no', 'uncertain') else 'uncertain',
                             event_type=a.get('event_type') if a.get('event_type') in EVENT_TYPES else 'other',
                             reason=a.get('reason', ''))
        done = min(i + batch, len(unique))
        if done % 50 < batch or done == len(unique):
            print(f"   {done}/{len(unique)} ({(time.perf_counter() - t0) / done:.1f}s per title)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='UTC day YYYY-MM-DD (default: yesterday)')
    ap.add_argument('--every', type=int, default=1, help='use 1 of every N 15-min files (testing only)')
    ap.add_argument('--model', default='qwen2.5:7b')
    ap.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    ap.add_argument('--batch', type=int, default=5)
    ap.add_argument('--no-llm', action='store_true', help='skip classification (plumbing test)')
    ap.add_argument('--out', default=os.path.join(ROOT, 'data', 'gkg'))
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    day = args.date or (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')

    records, stats, _, _ = collect(day, args.every)
    if args.no_llm:
        for r in records:
            r.update(relevant=None, event_type=None, reason=None)
    else:
        classify(records, args.model, args.endpoint, args.batch)

    flagged = 0
    for r in records:
        terms = removal_terms(r)
        r['removal_terms'] = terms
        r['review'] = bool(terms) and r['relevant'] in ('no', None)
        if r['review'] and r['relevant'] == 'no':
            r['relevant'] = 'uncertain'
        flagged += r['review']

    meta = {'collected_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'pipeline_version': PIPELINE_VERSION,
            'model': None if args.no_llm else args.model,
            'prompt_version': None if args.no_llm else PROMPT_VERSION,
            'every': args.every}
    folder = os.path.join(args.out, day[:4], day[5:7])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f'{day}.jsonl')
    keep = ('url', 'source', 'gkg_date', 'language', 'title', 'hit_theme', 'hit_name', 'hit_keyword',
            'locations', 'relevant', 'event_type', 'reason', 'removal_terms', 'review')
    with open(path, 'w', encoding='utf-8') as f:
        for r in sorted(records, key=lambda r: (r['gkg_date'], r['url'])):
            r['locations'] = r['locations'][:5]  # keeps the history file small
            f.write(json.dumps({**{k: r[k] for k in keep}, **meta}, ensure_ascii=False) + '\n')

    counts = Counter(r['relevant'] for r in records)
    print(f"\n{day}: {len(records)} candidates from {stats['files_ok']} files "
          f"({stats['files_missing']} missing) | relevant {dict(counts)} | flagged for review {flagged}")
    print(f"Saved {path}")
    if stats['files_ok'] == 0:
        sys.exit('No GKG files downloaded')


if __name__ == '__main__':
    main()
