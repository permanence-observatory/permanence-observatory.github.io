#!/usr/bin/env python3
"""
Input-scope experiment: does the model classify better with more input than production?

  arm A  (production): title, URL, language and the first 3 GKG locations
  arm B  (tested):     the same, plus all GKG locations, the GKG themes, and the
                       persons and organizations GDELT found in the article
  arm C  (this test):  arm A plus the first paragraphs of the article itself

The chosen arms run now, with the same model, batches and order, on stories a person has
already reviewed (blind) on the review page. The daily collector is not touched.

Steps:
  1. read the reviewed items and the reviewer's verdicts;
  2. download the GKG files of each item's day and keep the metadata of those URLs
     only (cached in --out, so a rerun skips the download);
  2b. (arm C) fetch each article in memory; only outcome and length are recorded;
  3. classify every item with each chosen arm;
  4. compare each arm with the human answer, and the arms with each other.

Usage:
  python prototype/input_scope_experiment.py \
      --items <dir with 2026-11-05_001.json ...> --verdicts <2026-11-05.json> \
      --items <dir ...> --verdicts <2026-11-08.json> --out <dir> [--model qwen2.5:7b]
  python prototype/input_scope_experiment.py --reviewed <out>/reviewed.json --out <out>
  --metadata-only   stop after step 2 (no model needed)
  --arms AC         which arms to run (default AB; e.g. AC or ABC). Arm C = arm A plus the
                    opening of the article itself, fetched with trafilatura. The article text
                    is kept in memory only and is never written to --out.
  --fetch-only      fetch the articles and report outcome and length per story, no model

The model needs about 6 GB of free memory; on a smaller machine run it in GitHub Actions
(.github/workflows/input-scope-experiment.yml), which reads prototype/data/input_scope/.
"""

import argparse
import csv
import glob
import io
import json
import os
import sys
import statistics
import time
import zipfile
from urllib.parse import urlparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify_llm import (DEFAULT_ENDPOINT, PROMPT_VERSION, SYSTEM_PROMPT,  # noqa: E402
                          call_model, normalize_answer)
from gkg_prototype import (BASE, C_LOCATIONS, C_THEMES, C_URL, FEEDS, download,  # noqa: E402
                           parse_locations, timestamps)

C_PERSONS, C_ORGANIZATIONS = 11, 13  # V1Persons, V1Organizations (GKG 2.1)
MAX_THEMES, MAX_NAMES, MAX_LOCATIONS = 30, 10, 10

ARM_B_NOTE = """

Some items also carry gdelt_themes, gdelt_persons and gdelt_organizations, and a longer
gdelt_locations list. GDELT extracted them automatically from the full article text, so they
tell what the article is about beyond its headline; use them as extra clues, but they are noisy."""

ARM_C_NOTE = """

Some items also carry article_start: the opening paragraphs of the article, extracted
automatically from the web page. It may be missing, truncated or contain page noise (menus,
cookie notices, ads); use it as an extra clue about what the article is about."""

ARTICLE_CHARS = 1200
FETCH_TIMEOUT = 20
FETCH_MAX_BYTES = 2_000_000
FETCH_UA = 'Mozilla/5.0 (compatible; research-fetch/1.0)'

HUMAN = {'sim': 'yes', 'nao': 'no', 'incerto': 'uncertain'}


def load_reviewed(items_dirs, verdict_files):
    """Reviewed items as dicts with the human answer; items without a verdict are skipped."""
    out = []
    for d, vf in zip(items_dirs, verdict_files):
        with open(vf, encoding='utf-8') as f:
            verdicts = json.load(f)['verdicts']
        for path in sorted(glob.glob(os.path.join(d, '*.json'))):
            item_id = os.path.splitext(os.path.basename(path))[0]
            v = verdicts.get(item_id)
            if not v or v.get('a') not in HUMAN:
                continue
            with open(path, encoding='utf-8') as f:
                it = json.load(f)
            out.append({'id': item_id, 'day': it['batch'], 'kind': it.get('kind', ''),
                        'title': it['title'], 'url': it['url'], 'language': it['language'],
                        'human_relevant': HUMAN[v['a']], 'human_removal': v.get('r') == 'sim',
                        'stored_model_relevant': (it.get('model') or {}).get('relevant', '')})
    return out


def unique(seq, limit):
    seen, out = set(), []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
            if len(out) == limit:
                break
    return out


def fetch_metadata(day, urls, workers=4):
    """GKG metadata of the given URLs on one UTC day (first row seen per URL)."""
    jobs = [f"{BASE}/{FEEDS[feed].format(ts=ts)}" for ts in timestamps(day, 1) for feed in FEEDS]
    found, missing = {}, 0
    with ThreadPoolExecutor(workers) as pool:
        for n, content in enumerate(pool.map(download, jobs), 1):
            if content is None:
                missing += 1
                continue
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                text = z.read(z.namelist()[0]).decode('utf-8', 'replace')
            for line in text.split('\n'):
                row = line.split('\t')
                if len(row) < 27 or row[C_URL] not in urls or row[C_URL] in found:
                    continue
                locations = parse_locations(row[C_LOCATIONS])
                found[row[C_URL]] = {
                    'locations': [l['name'] for l in locations],
                    'themes': unique((t for t in row[C_THEMES].split(';')), 10 ** 6),
                    'persons': unique((p for p in row[C_PERSONS].split(';')), 10 ** 6),
                    'organizations': unique((o for o in row[C_ORGANIZATIONS].split(';')), 10 ** 6),
                }
            if n % 24 == 0 or n == len(jobs):
                print(f'  {day}: {n}/{len(jobs)} files, {len(found)}/{len(urls)} URLs found', flush=True)
    return found, missing


def fetch_article(url):
    """Opening of the article at url. Returns (outcome, full_extracted_length, text).
    outcome: ok | http_<status> | timeout | empty | error. The text exists only in memory."""
    import requests
    import trafilatura
    if urlparse(url).scheme not in ('http', 'https'):
        return 'error', 0, ''
    try:
        with requests.get(url, timeout=FETCH_TIMEOUT, stream=True,
                          headers={'User-Agent': FETCH_UA, 'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.5'}) as r:
            if r.status_code >= 400:
                return f'http_{r.status_code}', 0, ''
            raw = r.raw.read(FETCH_MAX_BYTES + 1, decode_content=True)[:FETCH_MAX_BYTES]
            enc = r.encoding or r.apparent_encoding or 'utf-8'
    except requests.Timeout:
        return 'timeout', 0, ''
    except Exception:  # noqa: BLE001 - any network/TLS failure is just "error"
        return 'error', 0, ''
    try:
        html = raw.decode(enc, 'replace')
        text = trafilatura.extract(html, include_comments=False, include_tables=False) or ''
    except Exception:  # noqa: BLE001
        return 'error', 0, ''
    text = text.strip()
    if not text:
        return 'empty', 0, ''
    out = ''
    for para in (q.strip() for q in text.split('\n')):
        if not para:
            continue
        out += (' ' if out else '') + para
        if len(out) >= ARTICLE_CHARS:
            break
    return 'ok', len(text), out[:ARTICLE_CHARS]


def fetch_articles(items, workers=6):
    """{item id: (outcome, length, text)}, text in memory only."""
    with ThreadPoolExecutor(workers) as pool:
        got = list(pool.map(lambda it: fetch_article(it['url']), items))
    return {it['id']: r for it, r in zip(items, got)}


def fetch_report(items, fetched):
    """Outcome counts, failures by site and the median length; no article text."""
    host = lambda u: (urlparse(u).hostname or '').removeprefix('www.')  # noqa: E731
    outcomes = Counter(r[0] for r in fetched.values())
    lengths = [r[1] for r in fetched.values() if r[0] == 'ok']
    failures = Counter(f'{host(i["url"])} [{fetched[i["id"]][0]}]' for i in items if fetched[i['id']][0] != 'ok')
    return {
        'stories': len(items), 'outcomes': dict(outcomes),
        'success_rate': round(outcomes['ok'] / len(items), 3) if items else None,
        'median_extracted_chars': int(statistics.median(lengths)) if lengths else 0,
        'short_extractions_under_300_chars': sum(n < 300 for n in lengths),
        'failures_by_site': dict(failures.most_common()),
    }


def model_input(item, meta, arm, article=''):
    locs = meta['locations'] if meta else []
    x = {'id': item['id'], 'title': item['title'], 'url': item['url'], 'language': item['language']}
    if arm in ('A', 'C'):
        x['gdelt_locations'] = '; '.join(locs[:3])  # exactly what the collector sends
        if arm == 'C' and article:
            x['article_start'] = article
    else:
        x['gdelt_locations'] = '; '.join(unique(locs, MAX_LOCATIONS))
        x['gdelt_themes'] = (meta or {}).get('themes', [])[:MAX_THEMES]
        x['gdelt_persons'] = (meta or {}).get('persons', [])[:MAX_NAMES]
        x['gdelt_organizations'] = (meta or {}).get('organizations', [])[:MAX_NAMES]
    return x


def classify(items, metadata, arm, model, endpoint, batch, articles=None):
    prompt = SYSTEM_PROMPT + {'B': ARM_B_NOTE, 'C': ARM_C_NOTE}.get(arm, '')
    answers, tokens, t0 = {}, Counter(), time.perf_counter()
    for i in range(0, len(items), batch):
        group = items[i:i + batch]
        inputs = [model_input(it, metadata.get(it['url']), arm, (articles or {}).get(it['id'], ('', 0, ''))[2])
                  for it in group]
        got, usage = call_model(endpoint, model, inputs, system_prompt=prompt, fields=None)
        tokens.update({k: v for k, v in usage.items() if isinstance(v, int)})
        by_id = {str(a.get('id')): a for a in got if isinstance(a, dict)}
        for j, it in enumerate(group):
            a = by_id.get(it['id']) or (got[j] if len(got) == len(group) and isinstance(got[j], dict) else {})
            answers[it['id']] = {**normalize_answer(a), 'answered': bool(a)}
        done = min(i + batch, len(items))
        print(f'  arm {arm}: {done}/{len(items)} ({(time.perf_counter() - t0) / done:.1f}s per item)', flush=True)
    return answers, dict(tokens), time.perf_counter() - t0


def kept(a):
    """Same rule as the map: relevant 'yes' or a removal."""
    return a['relevant'] == 'yes' or a['removal'] is not None


def scores(items, answers):
    n = len(items)
    exact = sum(answers[i['id']]['relevant'] == i['human_relevant'] for i in items)
    tp = sum(kept(answers[i['id']]) and i['human_relevant'] == 'yes' for i in items)
    pp = sum(kept(answers[i['id']]) for i in items)
    ap = sum(i['human_relevant'] == 'yes' for i in items)
    rem_tp = sum(answers[i['id']]['removal'] is not None and i['human_removal'] for i in items)
    rem_pp = sum(answers[i['id']]['removal'] is not None for i in items)
    rem_ap = sum(i['human_removal'] for i in items)
    ratio = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {
        'items': n, 'relevance_exact_agreement': ratio(exact, n),
        'kept_precision': ratio(tp, pp), 'kept_recall': ratio(tp, ap), 'kept': pp, 'human_yes': ap,
        'removal_precision': ratio(rem_tp, rem_pp), 'removal_recall': ratio(rem_tp, rem_ap),
        'removal_predicted': rem_pp, 'removal_human': rem_ap,
        'confusion_human_to_model': {f'{h}->{m}': c for (h, m), c in sorted(Counter(
            (i['human_relevant'], answers[i['id']]['relevant']) for i in items).items())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--items', action='append', default=[], help='directory of review item files')
    ap.add_argument('--verdicts', action='append', default=[], help='verdict file for the same batch')
    ap.add_argument('--reviewed', help='reviewed.json written by an earlier run (instead of --items/--verdicts)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--model', default='qwen2.5:7b')
    ap.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    ap.add_argument('--batch', type=int, default=5)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--metadata-only', action='store_true')
    ap.add_argument('--arms', default='AB', help='arms to run, e.g. AB (default), AC, ABC')
    ap.add_argument('--fetch-only', action='store_true', help='only fetch articles (arm C input) and report')
    args = ap.parse_args()
    args.arms = ''.join(dict.fromkeys(args.arms.upper()))
    if not args.arms or set(args.arms) - set('ABC'):
        sys.exit('--arms takes the letters A, B, C')
    if args.reviewed:
        if args.items or args.verdicts:
            sys.exit('give --reviewed or --items/--verdicts, not both')
    elif not args.items or len(args.items) != len(args.verdicts):
        sys.exit('give --reviewed, or one --verdicts per --items')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    os.makedirs(args.out, exist_ok=True)

    if args.reviewed:
        with open(args.reviewed, encoding='utf-8') as f:
            items = json.load(f)
    else:
        items = load_reviewed(args.items, args.verdicts)
        items.sort(key=lambda i: i['id'])
        # The reviewed items without reviewer ids, so the test can be rerun elsewhere
        with open(os.path.join(args.out, 'reviewed.json'), 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=0)
    if args.limit:
        items = items[:args.limit]
    print(f'{len(items)} reviewed items: {dict(Counter(i["human_relevant"] for i in items))}')

    cache = os.path.join(args.out, 'gkg_metadata.json')
    metadata = {}
    if os.path.exists(cache):
        with open(cache, encoding='utf-8') as f:
            metadata = json.load(f)
    for day in sorted({i['day'] for i in items}):
        want = {i['url'] for i in items if i['day'] == day} - set(metadata)
        if want:
            found, missing = fetch_metadata(day, want)
            print(f'  {day}: {len(found)}/{len(want)} URLs found, {missing} GKG files missing')
            metadata.update(found)
            with open(cache, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False)
    no_meta = [i['id'] for i in items if i['url'] not in metadata]
    print(f'Metadata for {len(items) - len(no_meta)}/{len(items)} items; without: {no_meta}')
    lens = {k: [len(metadata[i['url']][k]) for i in items if i['url'] in metadata]
            for k in ('locations', 'themes', 'persons', 'organizations')}
    print('Median per item:', {k: sorted(v)[len(v) // 2] if v else 0 for k, v in lens.items()})
    if args.metadata_only:
        return

    articles, fetch_stats = None, None
    if 'C' in args.arms or args.fetch_only:
        print(f'Fetching {len(items)} articles (text kept in memory only)...', flush=True)
        articles = fetch_articles(items)
        fetch_stats = fetch_report(items, articles)
        print(json.dumps(fetch_stats, ensure_ascii=False, indent=2))
        per_story = [{'id': i['id'], 'outcome': articles[i['id']][0], 'chars': articles[i['id']][1]} for i in items]
        with open(os.path.join(args.out, 'fetch_outcomes.json'), 'w', encoding='utf-8') as f:
            json.dump({'summary': fetch_stats, 'stories': per_story}, f, ensure_ascii=False, indent=1)
    if args.fetch_only:
        return

    runs = {arm: classify(items, metadata, arm, args.model, args.endpoint, args.batch, articles)
            for arm in args.arms}
    ans = {arm: runs[arm][0] for arm in args.arms}

    ok = lambda arm, i: kept(ans[arm][i['id']]) == (i['human_relevant'] == 'yes')  # noqa: E731
    result = {
        'model': args.model, 'prompt_version': PROMPT_VERSION, 'batch': args.batch,
        'run_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'arms_run': args.arms,
        'items_without_metadata': no_meta,
        'arms': {arm: {**scores(items, ans[arm]), 'seconds': round(runs[arm][2]),
                       'tokens': runs[arm][1],
                       'unanswered': sum(not a['answered'] for a in ans[arm].values())} for arm in args.arms},
    }
    if fetch_stats:
        result['article_fetch'] = fetch_stats  # outcomes and lengths only, never article text
    base = 'A' if 'A' in args.arms else args.arms[0]
    # Paired (McNemar) discordant counts on the kept/not-kept decision against the human answer
    result['paired_vs_' + base] = {
        arm: {'agree_relevance': sum(ans[base][i['id']]['relevant'] == ans[arm][i['id']]['relevant'] for i in items),
              'agree_removal': sum((ans[base][i['id']]['removal'] is None) == (ans[arm][i['id']]['removal'] is None)
                                   for i in items),
              f'only_{base}_right': sum(ok(base, i) and not ok(arm, i) for i in items),
              f'only_{arm}_right': sum(ok(arm, i) and not ok(base, i) for i in items)}
        for arm in args.arms if arm != base}
    if 'C' in args.arms and base != 'C':
        got = [i for i in items if articles[i['id']][0] == 'ok']
        result['arm_C_only_stories_with_article'] = {
            'items': len(got),
            f'only_{base}_right': sum(ok(base, i) and not ok('C', i) for i in got),
            'only_C_right': sum(ok('C', i) and not ok(base, i) for i in got)}
    if 'A' in args.arms:
        result['arm_A_reproduces_stored'] = sum(ans['A'][i['id']]['relevant'] == i['stored_model_relevant']
                                                for i in items if i['stored_model_relevant'])
    with open(os.path.join(args.out, 'input_scope_result.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, 'input_scope_items.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        head = ['id', 'kind', 'language', 'title', 'url', 'human_relevant', 'human_removal']
        for arm in args.arms:
            head += [f'{arm}_relevant', f'{arm}_removal', f'{arm}_reason']
        if 'C' in args.arms:
            head += ['C_fetch_outcome', 'C_article_chars']
        if 'B' in args.arms:
            head += ['gdelt_themes', 'gdelt_persons', 'gdelt_organizations']
        w.writerow(head)
        for i in items:
            m = metadata.get(i['url'], {})
            row = [i['id'], i['kind'], i['language'], i['title'], i['url'], i['human_relevant'], i['human_removal']]
            for arm in args.arms:
                a = ans[arm][i['id']]
                row += [a['relevant'], a['removal'] or '', a['reason']]
            if 'C' in args.arms:
                row += [articles[i['id']][0], articles[i['id']][1]]
            if 'B' in args.arms:
                row += ['; '.join(m.get('themes', [])[:MAX_THEMES]), '; '.join(m.get('persons', [])[:MAX_NAMES]),
                        '; '.join(m.get('organizations', [])[:MAX_NAMES])]
            w.writerow(row)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
