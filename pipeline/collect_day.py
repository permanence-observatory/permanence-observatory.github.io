#!/usr/bin/env python3
"""
Daily collector: GDELT GKG raw files -> pre-filter -> language model -> daily history file.

Runs alongside the current map (gdelt_version_v21.py) without touching it. For one
UTC day it:
  1. downloads the 96 GKG files (English + translated feeds) and keeps candidates
     that match the SLUMS theme, a settlement name (checked against the GKG
     locations) or a keyword  -- same filter as prototype/gkg_prototype.py;
  2. classifies each unique title with a local open model served by Ollama
     (broad relevance, one or more topics, and whether it is a removal story and
     at which stage), using the prompt in prototype/classify_llm.py;
  3. never lets a removal story be dropped silently: if the title or URL has a
     removal word (eviction, desalojo, despejo, déguerpissement...) and the model
     did not call it a removal, the record is flagged for review (and a "no"
     becomes "uncertain");
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
from classify_llm import (DEFAULT_ENDPOINT, PROMPT_VERSION, call_model,  # noqa: E402
                          normalize_answer)
from gkg_prototype import (AMBIGUOUS_NAMES, STRONG_REMOVAL_RE, WEAK_REMOVAL_RE,  # noqa: E402
                           collect, fold, url_text)

PIPELINE_VERSION = '2026-11-11.2'
UNCLASSIFIED = {'relevant': None, 'topics': [], 'removal': None, 'place': '', 'reason': None}

# Settlement names that are whole districts or municipalities: seeing one in a
# headline says nothing about an informal settlement.
LARGE_DISTRICTS = {
    'ecatepec', 'iztapalapa', 'tlahuac', 'soweto', 'khayelitsha', 'mitchells plain',
    'villa el salvador', 'el alto', 'ciudad bolivar', 'soacha', 'pikine', 'guediawaye',
}


def removal_check(record, ambiguous_names):
    """Return (terms, flag): flag is True when the record looks like a removal story.
    Strong word + any settlement evidence (theme, keyword, a specific name in the
    title/URL, or a housing word, which is how removal-only entries got in) flags it;
    a weak word needs a keyword or specific name in the title/URL."""
    text = fold(f"{record['title']} {url_text(record['url'])}")
    strong = set(STRONG_REMOVAL_RE.findall(text))
    weak = set(WEAK_REMOVAL_RE.findall(text)) - strong
    specific_name = any(n in text for n in record['hit_name']
                        if n not in LARGE_DISTRICTS and n not in ambiguous_names)
    in_title = bool(record['hit_keyword']) or specific_name
    flag = (bool(strong and (in_title or record['hit_theme'] or record.get('hit_removal')))
            or bool(weak and in_title))
    return sorted(strong | weak), flag


def assign_stories(records, day, min_shared=3, max_df=0.05):
    """Group records that tell the same story. Two titles are linked when they share
    at least min_shared words that are rare that day (in at most max_df of titles),
    or a rare two-word proper name ("Kim Liên", "Los Asperones").
    Approximate: catches reprints and rewrites in the same language."""
    words = [set(w for w in re.findall(r'\w+', fold(r['title'])) if len(w) >= 3 and not w.isdigit())
             for r in records]
    df = Counter(w for ws in words for w in ws)
    limit = max(3, max_df * len(records))
    rare = [{w for w in ws if df[w] <= limit} for ws in words]
    # Two capitalized words in a row; a big story makes its own name common, so
    # names get a looser limit than single words
    names = []
    for r in records:
        tokens = re.findall(r'\w+', r['title'])
        names.append({f'{fold(a)} {fold(b)}' for a, b in zip(tokens, tokens[1:])
                      if a[:1].isupper() and b[:1].isupper() and len(a) >= 3 and len(b) >= 3})
    name_df = Counter(n for ns in names for n in ns)
    for ws, ns in zip(rare, names):
        ws.update(n for n in ns if name_df[n] <= 3 * limit)  # counts as enough on its own, see below
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_word = {}
    for i, ws in enumerate(rare):
        for w in ws:
            by_word.setdefault(w, []).append(i)
    shared = Counter()
    for w, idx in by_word.items():
        weight = min_shared if ' ' in w else 1  # a shared proper name links on its own
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                shared[(idx[a], idx[b])] += weight
    for (a, b), n in shared.items():
        if n >= min_shared or (records[a]['title'] and records[a]['title'].lower() == records[b]['title'].lower()):
            parent[find(a)] = find(b)
    ids = {}
    for i, r in enumerate(records):
        r['story_id'] = f"{day}-{ids.setdefault(find(i), len(ids) + 1):04d}"


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
            answer = UNCLASSIFIED if a is None else normalize_answer(a)
            for r in g:
                r.update({**answer, 'topics': list(answer['topics'])})
        done = min(i + batch, len(unique))
        if done % 50 < batch or done == len(unique):
            print(f"   {done}/{len(unique)} ({(time.perf_counter() - t0) / done:.1f}s per title)", flush=True)


def summarize(records, day):
    """Daily numbers for monitoring: a sudden jump or drop points to a problem."""
    relevant = [r for r in records if r['relevant'] == 'yes']
    stories = {}
    for r in relevant:
        stories.setdefault(r['story_id'], []).append(r)
    removals = [g for g in stories.values() if any(r['removal'] for r in g)]
    return {
        'date': day,
        'candidates': len(records),
        'relevant': dict(Counter(str(r['relevant']) for r in records)),
        'stories_relevant': len(stories),
        'stories_removal': len(removals),
        'flagged_for_review': sum(r['review'] for r in records),
        'topics_by_story': dict(Counter(t for g in stories.values()
                                        for t in {t for r in g for t in r['topics']}).most_common()),
        'removal_stories': [{'story_id': g[0]['story_id'], 'stage': next(r['removal'] for r in g if r['removal']),
                             'title': g[0]['title']} for g in removals],
        'languages_relevant': dict(Counter(r['language'] for r in relevant).most_common()),
        'top_stories': [{'story_id': sid, 'records': len(g), 'title': g[0]['title']}
                        for sid, g in sorted(stories.items(), key=lambda kv: -len(kv[1]))[:10]],
    }


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
    t_start = time.perf_counter()

    records, stats, _, _ = collect(day, args.every)
    if args.no_llm:
        for r in records:
            r.update({**UNCLASSIFIED, 'topics': []})
    else:
        classify(records, args.model, args.endpoint, args.batch)

    flagged = 0
    for r in records:
        terms, looks_like_removal = removal_check(r, AMBIGUOUS_NAMES)
        r['removal_terms'] = terms
        # A possible removal the model did not call one goes to review
        r['review'] = looks_like_removal and not r['removal']
        if r['review'] and r['relevant'] == 'no':
            r['relevant'] = 'uncertain'
        flagged += r['review']
    assign_stories(records, day)

    meta = {'collected_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'pipeline_version': PIPELINE_VERSION,
            'model': None if args.no_llm else args.model,
            'prompt_version': None if args.no_llm else PROMPT_VERSION,
            'every': args.every}
    folder = os.path.join(args.out, day[:4], day[5:7])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f'{day}.jsonl')
    keep = ('url', 'source', 'gkg_date', 'language', 'title', 'story_id', 'hit_theme', 'hit_name', 'hit_keyword',
            'hit_removal',
            'locations', 'relevant', 'topics', 'removal', 'place', 'reason', 'removal_terms', 'review')
    with open(path, 'w', encoding='utf-8') as f:
        for r in sorted(records, key=lambda r: (r['gkg_date'], r['url'])):
            r['locations'] = r['locations'][:5]  # keeps the history file small
            f.write(json.dumps({**{k: r[k] for k in keep}, **meta}, ensure_ascii=False) + '\n')

    summary = summarize(records, day)
    summary.update(meta, files_ok=stats['files_ok'], files_missing=stats['files_missing'],
                   seconds_total=round(time.perf_counter() - t_start))
    with open(os.path.join(folder, f'{day}.summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{day}: {len(records)} candidates from {stats['files_ok']} files ({stats['files_missing']} missing)")
    print(json.dumps({k: summary[k] for k in ('relevant', 'stories_relevant', 'stories_removal', 'flagged_for_review')},
                     ensure_ascii=False))
    print(f"Saved {path}")
    # Fail the run (and so raise the alert) when the day is clearly incomplete
    expected = 2 * len(range(0, 96, args.every))
    if stats['files_ok'] == 0 or not records:
        sys.exit('No GKG files or no candidates: the day is missing')
    if stats['files_missing'] > expected / 4:
        sys.exit(f"{stats['files_missing']} of {expected} GKG files missing: the day is incomplete")
    unclassified = sum(r['relevant'] is None for r in records)
    if not args.no_llm and unclassified > len(records) / 5:
        sys.exit(f'{unclassified} of {len(records)} candidates left unclassified: check the model server')


if __name__ == '__main__':
    main()
