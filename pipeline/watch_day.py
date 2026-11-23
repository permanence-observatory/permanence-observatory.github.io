#!/usr/bin/env python3
"""
Daily watch: is a day out of line with the days before it, and if so, is it a real rise
in news that deserves attention, or a data problem like the 2026-11-20 iHeart reprints?

1. Rates per 100,000 GKG articles (so weekends and volume swings do not count) for
   candidates, relevant stories and eviction stories, compared with the previous
   BASELINE_DAYS days by a robust z-score (median and MAD).
2. Where the day's numbers come from: share of the largest source, the most repeated
   headline, the place with most stories, how many sources, languages and countries.
3. Collector health: missing GKG files, unclassified candidates.

Verdict:
  data_problem  the map is likely wrong: collector health failed, a relevant headline split over
                several stories (grouping failure), or one place with many relevant stories;
                the workflow opens an issue;
  artefact      mass reprints (one source or one headline behind a large share of the
                candidates) that inflate the candidates but are grouped into one story each,
                so the map is not distorted; shown on the dashboard, no issue;
  real_rise     a story or eviction rate is unusually high and the excess is spread over many
                sources and stories;
  low           a rate is unusually low with a healthy collector (worth a look, often quiet news);
  normal        otherwise; also when there are too few earlier days to compare.

Writes data/gkg/AAAA/MM/AAAA-MM-DD.watch.json; build_map_data.py copies the verdict to
mapa/stats.json. Exit code 0 always; the workflow opens an issue on data_problem.

Usage:
  python pipeline/watch_day.py --date 2026-11-20
  python pipeline/watch_day.py --all            # every saved day (only earlier days as baseline)
  python pipeline/watch_day.py --all --data <dir> --dry-run
"""

import argparse
import glob
import json
import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect_day import title_key  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
BASELINE_DAYS = 14
MIN_BASELINE = 5      # fewer earlier days: no verdict on rates
Z_HIGH = 3.5          # robust z-score that counts as unusual
MIN_RATIO = 1.5       # ... and at least this times the median
# Concentrations no ordinary day shows (checked on the history of 2026-11-05 to 11-21)
TOP_SOURCE_SHARE = 0.25     # one source behind this share of the candidates
TOP_SOURCE_MIN = 50         # ... with at least this many candidates
REPEATED_TITLE_MIN = 50     # one headline repeated this many times
PLACE_STORIES_MAX = 15      # one place with this many relevant stories
SPLIT_TITLE_STORIES = 3     # one headline split over this many stories (grouping failure)
MISSING_FILES_MAX = 0.05    # share of GKG files missing
UNCLASSIFIED_MAX = 0.05     # share of candidates without a model answer


def load_day(path):
    with open(path, encoding='utf-8') as f:
        records = [json.loads(line) for line in f if line.strip()]
    spath = path[:-len('.jsonl')] + '.summary.json'
    summary = {}
    if os.path.exists(spath):
        with open(spath, encoding='utf-8') as f:
            summary = json.load(f)
    return records, summary


def kept(r):
    return r.get('relevant') == 'yes' or bool(r.get('removal'))


def measure(records, summary):
    """Counts, rates and concentration figures of one day."""
    stories, removal_stories = {}, set()
    for r in records:
        if kept(r):
            sid = r.get('story_id') or r['url']
            stories.setdefault(sid, []).append(r)
            if r.get('removal'):
                removal_stories.add(sid)
    gkg = (summary.get('gkg_articles') or {}).get('total')
    rate = (lambda n: round(n / gkg * 1e5, 2)) if gkg else (lambda n: None)

    sources = Counter(r.get('source') or '' for r in records)
    top_source, top_source_n = sources.most_common(1)[0] if sources else ('', 0)
    keys = Counter(title_key(r.get('title')) for r in records if r.get('title'))
    top_title, top_title_n = keys.most_common(1)[0] if keys else ('', 0)
    title_stories = {}  # relevant headlines only: a split there distorts the map
    for r in records:
        if r.get('title') and kept(r):
            title_stories.setdefault(title_key(r['title']), set()).add(r.get('story_id'))
    split = max((len(v) for v in title_stories.values()), default=0)
    faces = [next((r for r in g if r.get('removal')), g[0]) for g in stories.values()]
    places = Counter((f.get('place') or '').strip() for f in faces if (f.get('place') or '').strip())
    top_place, top_place_n = places.most_common(1)[0] if places else ('', 0)
    kept_sources = Counter(r.get('source') or '' for g in stories.values() for r in g)
    hhi = sum((n / sum(kept_sources.values())) ** 2 for n in kept_sources.values()) if kept_sources else 0
    files_ok, files_missing = summary.get('files_ok'), summary.get('files_missing')
    unclassified = sum(r.get('relevant') is None for r in records)
    return {
        'candidates': len(records), 'stories': len(stories), 'eviction_stories': len(removal_stories),
        'gkg_articles': gkg,
        'rate_candidates': rate(len(records)), 'rate_stories': rate(len(stories)),
        'rate_evictions': rate(len(removal_stories)),
        'top_source': top_source, 'top_source_candidates': top_source_n,
        'top_source_share': round(top_source_n / len(records), 3) if records else 0,
        'top_title': top_title[:120], 'top_title_records': top_title_n,
        'max_stories_per_title': split,
        'top_place': top_place, 'top_place_stories': top_place_n,
        'sources_of_kept': len(kept_sources), 'effective_sources_of_kept': round(1 / hhi, 1) if hhi else 0,
        'languages_of_kept': len({f.get('language') for f in faces}),
        'countries_of_kept': len({(f.get('place') or '').split(',')[-1].strip() for f in faces if f.get('place')}),
        'files_missing_share': round(files_missing / (files_ok + files_missing), 3)
        if files_ok is not None and files_missing is not None and files_ok + files_missing else None,
        'unclassified_share': round(unclassified / len(records), 3) if records else 0,
    }


def robust_z(x, history):
    if x is None:
        return None, None
    vals = [v for v in history if v is not None]
    if len(vals) < MIN_BASELINE:
        return None, None
    med = statistics.median(vals)
    mad = statistics.median(abs(v - med) for v in vals) or max(0.05 * med, 1e-9)
    return round((x - med) / (1.4826 * mad), 1), med


def judge(day, m, history):
    """Verdict and reasons for one day, given the measures of the earlier days."""
    reasons, high, low = [], [], []
    rates = {}
    for key, label in (('rate_candidates', 'candidates'), ('rate_stories', 'relevant stories'),
                       ('rate_evictions', 'eviction stories')):
        z, med = robust_z(m[key], [h[key] for h in history])
        rates[key] = {'value': m[key], 'baseline_median': med, 'z': z}
        if z is None:
            continue
        if z >= Z_HIGH and m[key] >= MIN_RATIO * med:
            high.append(f'{label}: {m[key]} per 100k articles, {m[key] / med:.1f}x the median of the last {len(history)} days')
        elif z <= -Z_HIGH and m[key] <= med / MIN_RATIO:
            low.append(f'{label}: {m[key]} per 100k articles, {m[key] / med:.2f}x the median')

    data, artefact = [], []
    if m['files_missing_share'] is not None and m['files_missing_share'] > MISSING_FILES_MAX:
        data.append(f"{m['files_missing_share']:.0%} of the GKG files missing")
    if m['unclassified_share'] > UNCLASSIFIED_MAX:
        data.append(f"{m['unclassified_share']:.0%} of the candidates without a model answer")
    if m['top_source_share'] >= TOP_SOURCE_SHARE and m['top_source_candidates'] >= TOP_SOURCE_MIN:
        artefact.append(f"one source, {m['top_source']}, gave {m['top_source_candidates']} of the "
                    f"{m['candidates']} candidates ({m['top_source_share']:.0%})")
    if m['top_title_records'] >= REPEATED_TITLE_MIN:
        artefact.append(f"one headline repeated {m['top_title_records']} times: \"{m['top_title'][:80]}\"")
    if m['max_stories_per_title'] >= SPLIT_TITLE_STORIES:
        data.append(f"one relevant headline split over {m['max_stories_per_title']} stories (grouping failure)")
    if m['top_place_stories'] >= PLACE_STORIES_MAX:
        data.append(f"{m['top_place_stories']} relevant stories at one place: {m['top_place']}")

    # A rise in candidates alone, with mass reprints, is the reprints, not news
    story_high = [h for h in high if not h.startswith('candidates')]
    if data:
        status = 'data_problem'
        reasons = data + artefact + high + low
    elif artefact and not story_high:
        status = 'artefact'
        reasons = artefact + high + ['stories and evictions within the usual range: the reprints are grouped']
    elif story_high:
        status = 'real_rise'
        reasons = story_high + [f"spread over {m['sources_of_kept']} sources "
                                f"({m['effective_sources_of_kept']} effective), {m['languages_of_kept']} languages "
                                f"and {m['countries_of_kept']} countries"] + artefact
    elif high:
        status = 'normal'
        reasons = high + ['more candidates, but relevant and eviction stories within the usual range']
    elif low:
        status, reasons = 'low', low
    else:
        status = 'normal'
        if len(history) < MIN_BASELINE:
            reasons = [f'only {len(history)} earlier days: rates not compared']
    return {'date': day, 'status': status, 'reasons': reasons, 'rates': rates, 'measures': m,
            'baseline_days': [h['date'] for h in history]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', help='UTC day YYYY-MM-DD')
    ap.add_argument('--all', action='store_true', help='every saved day')
    ap.add_argument('--data', default=os.path.join(ROOT, 'data', 'gkg'))
    ap.add_argument('--dry-run', action='store_true', help='print, write nothing')
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if not args.date and not args.all:
        sys.exit('give --date or --all')

    paths = sorted(glob.glob(os.path.join(args.data, '*', '*', '*.jsonl')))
    days = [os.path.basename(p)[:10] for p in paths]
    targets = days if args.all else [args.date]
    measures = {}
    for day in targets:
        if day not in days:
            sys.exit(f'no history file for {day}')
        i = days.index(day)
        for d, p in zip(days[max(0, i - BASELINE_DAYS):i + 1], paths[max(0, i - BASELINE_DAYS):i + 1]):
            if d not in measures:
                measures[d] = {'date': d, **measure(*load_day(p))}
        history = [measures[d] for d in days[max(0, i - BASELINE_DAYS):i]]
        verdict = judge(day, measures[day], history)
        print(f"{day}: {verdict['status']}" + ''.join(f'\n    - {r}' for r in verdict['reasons']))
        if not args.dry_run:
            out = paths[i][:-len('.jsonl')] + '.watch.json'
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(verdict, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
