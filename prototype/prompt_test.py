#!/usr/bin/env python3
"""
Prompt test: the production instructions (classify_llm.SYSTEM_PROMPT) against a candidate
that separates ordinary evictions from removals in informal settlements.

Candidate changes (2026-11-23):
  - "no" also covers housing news with no informal settlement involved: tenant or mortgage
    evictions, squatters removed from a single house or apartment, demolition of heritage or
    private buildings, buildings evacuated because they are unsafe;
  - removal is only the removal of homes in an informal settlement: shacks, squatter or
    irregular settlements, camps where people live (including homeless encampments) and
    buildings occupied by many families; housing protest camps are not settlements.

Two sets, both classified with both prompts by the same model, batches and order:
  reviewed  stories reviewed blind (prototype/data/input_scope/reviewed.json): agreement,
            precision and recall against the human answers;
  targeted  eviction stories from the history (--build-targeted): all placed in the Global
            North, where most ordinary evictions are, plus a random sample from the rest.
            No human labels: the output lists every story whose answer changed, for review.

Usage:
  python prototype/prompt_test.py --build-targeted          # writes the targeted set
  python prototype/prompt_test.py --out <dir> [--model qwen2.5:7b] [--limit N]
"""

import argparse
import csv
import glob
import json
import os
import random
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
from classify_llm import DEFAULT_ENDPOINT, PROMPT_VERSION, SYSTEM_PROMPT, call_model, normalize_answer  # noqa: E402
from input_scope_experiment import HUMAN, kept, scores  # noqa: E402,F401

DATA = os.path.join(HERE, 'data', 'prompt_test')
REVIEWED = os.path.join(HERE, 'data', 'input_scope', 'reviewed.json')
GKG_META = os.path.join(HERE, 'data', 'input_scope', 'gkg_metadata.json')
CANDIDATE_VERSION = '2026-11-23.c1'

# Last part of the model's place; UN M49 developed regions, as on the map
NORTH = {'United States', 'Canada', 'United Kingdom', 'Ireland', 'Spain', 'Portugal', 'France', 'Germany',
         'Italy', 'Netherlands', 'Belgium', 'Luxembourg', 'Switzerland', 'Austria', 'Denmark', 'Norway',
         'Sweden', 'Finland', 'Iceland', 'Greece', 'Poland', 'Czechia', 'Czech Republic', 'Slovakia', 'Hungary',
         'Slovenia', 'Croatia', 'Romania', 'Bulgaria', 'Estonia', 'Latvia', 'Lithuania', 'Malta', 'Cyprus',
         'Japan', 'Australia', 'New Zealand', 'Israel'}


def candidate_prompt():
    """The production prompt with the two edits; fails loudly if the base text changed."""
    p = SYSTEM_PROMPT
    edits = [
        ('or another unrelated meaning of the word.',
         'or another unrelated meaning of the word. Also "no" for housing news with no informal\n'
         '        settlement involved: a tenant or family evicted from a rented or mortgaged home,\n'
         '        squatters removed from a single house or apartment, a heritage or private building\n'
         '        demolished, or a building evacuated because it is unsafe.'),
        ('removal: "none" unless the article is about removing homes in an informal settlement. Then:',
         'removal: "none" unless homes in an informal settlement are removed: shacks, a squatter or\n'
         '  irregular settlement, or a camp or occupied building where many families live (homeless\n'
         '  encampments count; housing protest camps do not). Ordinary evictions (tenants, mortgages,\n'
         '  squatters in a single house) and demolitions of formal buildings are "none". Then:'),
    ]
    for old, new in edits:
        if p.count(old) != 1:
            sys.exit(f'base prompt changed, edit not applied: {old!r}')
        p = p.replace(old, new)
    return p


def build_targeted(seed=1, south_n=60):
    """Eviction stories (one face per story) from the saved history."""
    stories = {}
    for path in sorted(glob.glob(os.path.join(ROOT, 'data', 'gkg', '*', '*', '*.jsonl'))):
        with open(path, encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                if r.get('removal') and r['story_id'] not in stories:
                    stories[r['story_id']] = r
    north, south = [], []
    for sid, r in sorted(stories.items()):
        country = (r.get('place') or '').split(',')[-1].strip()
        item = {'id': sid, 'title': r['title'], 'url': r['url'], 'language': r['language'],
                'gdelt_locations': '; '.join(l['name'] for l in r['locations'][:3]),
                'place': r.get('place', ''), 'stored_relevant': r['relevant'], 'stored_removal': r['removal'],
                'stored_prompt': r.get('prompt_version')}
        (north if country in NORTH else south).append({**item, 'group': 'north' if country in NORTH else 'south'})
    rng = random.Random(seed)
    sample = rng.sample(south, min(south_n, len(south)))
    os.makedirs(DATA, exist_ok=True)
    out = os.path.join(DATA, 'targeted_2026-11-23.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(north + sample, f, ensure_ascii=False, indent=0)
    print(f'{len(stories)} eviction stories: {len(north)} in the Global North (all kept), '
          f'{len(south)} elsewhere ({len(sample)} sampled) -> {out}')


def run(items, prompt, model, endpoint, batch, label):
    answers, tokens, t0 = {}, Counter(), time.perf_counter()
    for i in range(0, len(items), batch):
        group = items[i:i + batch]
        got, usage = call_model(endpoint, model, group, system_prompt=prompt)
        tokens.update({k: v for k, v in usage.items() if isinstance(v, int)})
        by_id = {str(a.get('id')): a for a in got if isinstance(a, dict)}
        for j, it in enumerate(group):
            a = by_id.get(it['id']) or (got[j] if len(got) == len(group) and isinstance(got[j], dict) else {})
            answers[it['id']] = {**normalize_answer(a), 'answered': bool(a)}
        done = min(i + batch, len(items))
        print(f'  {label}: {done}/{len(items)} ({(time.perf_counter() - t0) / done:.1f}s per item)', flush=True)
    return answers, dict(tokens), round(time.perf_counter() - t0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build-targeted', action='store_true')
    ap.add_argument('--targeted', default=os.path.join(DATA, 'targeted_2026-11-23.json'))
    ap.add_argument('--out')
    ap.add_argument('--model', default='qwen2.5:7b')
    ap.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    ap.add_argument('--batch', type=int, default=5)
    ap.add_argument('--limit', type=int, help='first N items of each set (quick check)')
    ap.add_argument('--show-prompt', action='store_true')
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if args.build_targeted:
        return build_targeted()
    cand = candidate_prompt()
    if args.show_prompt:
        print(cand)
        return
    if not args.out:
        sys.exit('--out is required')
    os.makedirs(args.out, exist_ok=True)

    with open(REVIEWED, encoding='utf-8') as f:
        reviewed = json.load(f)
    with open(GKG_META, encoding='utf-8') as f:
        meta = json.load(f)
    for it in reviewed:
        it['gdelt_locations'] = '; '.join((meta.get(it['url']) or {}).get('locations', [])[:3])
    with open(args.targeted, encoding='utf-8') as f:
        targeted = json.load(f)
    if args.limit:
        reviewed, targeted = reviewed[:args.limit], targeted[:args.limit]

    res = {'model': args.model, 'base_prompt': PROMPT_VERSION, 'candidate_prompt': CANDIDATE_VERSION,
           'run_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'sets': {}}
    rows = []
    for name, items in (('reviewed', reviewed), ('targeted', targeted)):
        base = run(items, SYSTEM_PROMPT, args.model, args.endpoint, args.batch, f'{name} base')
        new = run(items, cand, args.model, args.endpoint, args.batch, f'{name} candidate')
        b, c = base[0], new[0]
        s = {'items': len(items), 'seconds': {'base': base[2], 'candidate': new[2]},
             'tokens': {'base': base[1], 'candidate': new[1]},
             'unanswered': {'base': sum(not a['answered'] for a in b.values()),
                            'candidate': sum(not a['answered'] for a in c.values())}}
        if name == 'reviewed':
            s['base'] = scores(items, b)
            s['candidate'] = scores(items, c)
            ok = lambda ans, i: kept(ans[i['id']]) == (i['human_relevant'] == 'yes')  # noqa: E731
            s['only_base_right'] = sum(ok(b, i) and not ok(c, i) for i in items)
            s['only_candidate_right'] = sum(ok(c, i) and not ok(b, i) for i in items)
        else:
            for g in ('north', 'south'):
                sub = [i for i in items if i['group'] == g]
                s[g] = {'items': len(sub),
                        'removal_base': sum(b[i['id']]['removal'] is not None for i in sub),
                        'removal_candidate': sum(c[i['id']]['removal'] is not None for i in sub),
                        'relevant_base': sum(b[i['id']]['relevant'] == 'yes' for i in sub),
                        'relevant_candidate': sum(c[i['id']]['relevant'] == 'yes' for i in sub)}
        res['sets'][name] = s
        for i in items:
            x, y = b[i['id']], c[i['id']]
            if (x['relevant'], x['removal']) != (y['relevant'], y['removal']):
                rows.append([name, i.get('group', ''), i['id'], i['language'], i['title'], i['url'],
                             i.get('human_relevant', ''), i.get('human_removal', ''),
                             x['relevant'], x['removal'] or '', x['reason'], y['relevant'], y['removal'] or '', y['reason']])

    with open(os.path.join(args.out, 'prompt_test_result.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, 'prompt_test_changed.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['set', 'group', 'id', 'language', 'title', 'url', 'human_relevant', 'human_removal',
                    'base_relevant', 'base_removal', 'base_reason', 'cand_relevant', 'cand_removal', 'cand_reason'])
        w.writerows(rows)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f'{len(rows)} stories changed answer -> prompt_test_changed.csv')


if __name__ == '__main__':
    main()
