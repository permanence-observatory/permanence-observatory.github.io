#!/usr/bin/env python3
"""
Classify candidate news with a language model and compare with the
reference labels.

Talks to any OpenAI-compatible chat endpoint. The default is a local Ollama
server running an open model, so it costs nothing and depends on no external
service; the same setup can run inside a GitHub Actions runner. An API key is
only sent if LLM_API_KEY is set (for a hosted endpoint).

Usage:
  ollama pull gemma3:4b
  python prototype/classify_llm.py prototype/output/reference_2026-11-02.csv --model gemma3:4b
  python prototype/classify_llm.py ... --limit 10        # quick check
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter

import requests

DEFAULT_ENDPOINT = 'http://localhost:11434/v1/chat/completions'
PROMPT_VERSION = '2026-11-02.1'

EVENT_TYPES = {
    'eviction': 'Despejo/remoção', 'demolition': 'Demolição', 'protest': 'Protesto',
    'fire': 'Incêndio', 'flood_landslide': 'Enchente/deslizamento', 'land_conflict': 'Conflito fundiário',
    'health': 'Saúde/doença', 'violence_policing': 'Violência/operação policial',
    'upgrading_infrastructure': 'Urbanização/infraestrutura', 'housing_policy': 'Política habitacional',
    'other': 'Outro', 'not_applicable': 'Não se aplica',
}
RELEVANT = {'yes': 'Sim', 'no': 'Não', 'uncertain': 'Incerto'}

SYSTEM_PROMPT = f"""You screen news headlines for an observatory that documents informal settlements
(slums, favelas, shantytowns, squatter or irregular settlements, villas miseria, barriadas,
asentamientos, bidonvilles, katchi abadis, South African informal settlements) to protect
residents from eviction.

For each item decide:
relevant:
  "yes" only if an informal settlement, or its residents as residents of it, is the CENTRAL
        subject of the article (e.g. eviction or demolition of a favela, fire in a shantytown,
        police operation inside a favela, slum upgrading policy, data on slum population).
  "no"  if the matching word is a coincidence (person, sports club, US "township" municipality,
        planned "township" development, generic "community", ordinary neighbourhood called
        "barriada"), or the settlement is only a backdrop to a city-wide or unrelated story.
  "uncertain" only when the headline genuinely cannot be decided either way.
event_type: one of {', '.join(EVENT_TYPES)}. Use "not_applicable" when relevant is "no".
reason: at most 20 words, in Portuguese.

Headlines can be in any language. Use the URL words and the GDELT locations as extra clues,
but GDELT locations are often wrong. Answer only with JSON:
{{"items": [{{"id": "...", "relevant": "...", "event_type": "...", "reason": "..."}}]}}"""


def call_model(endpoint, model, items, max_retries=4):
    user = json.dumps([{k: it[k] for k in ('id', 'title', 'url', 'language', 'gdelt_locations')}
                       for it in items], ensure_ascii=False)
    body = {
        'model': model, 'temperature': 0,
        'response_format': {'type': 'json_object'},
        'messages': [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': user}],
    }
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if os.environ.get('LLM_API_KEY'):
        headers['Authorization'] = f"Bearer {os.environ['LLM_API_KEY']}"
    for attempt in range(max_retries):
        r = requests.post(endpoint, headers=headers, json=body, timeout=900)
        if r.status_code == 429:
            wait = int(r.headers.get('retry-after', 30 * (attempt + 1)))
            print(f'   rate limited, waiting {wait}s', flush=True)
            time.sleep(min(wait, 300))
            continue
        if r.status_code != 200 or not r.headers.get('content-type', '').startswith('application/json'):
            raise RuntimeError(f"HTTP {r.status_code} ({r.headers.get('content-type')}): {r.text[:300]}")
        data = r.json()
        content = data['choices'][0]['message']['content']
        try:
            return json.loads(content).get('items', []), data.get('usage', {})
        except json.JSONDecodeError:
            # Small models sometimes wrap JSON in text; take the outermost object, else retry
            m = re.search(r'\{.*\}', content, re.S)
            if m:
                try:
                    return json.loads(m.group(0)).get('items', []), data.get('usage', {})
                except json.JSONDecodeError:
                    pass
            print(f'   unparseable answer, retrying: {content[:120]!r}', flush=True)
    raise RuntimeError('model did not return usable JSON')


def report(rows, source):
    sub = [r for r in rows if r['label_source'] == source and r.get('pred_relevant')]
    if not sub:
        return
    agree = sum(r['relevant'] == r['pred_relevant'] for r in sub)
    print(f'\n== {source}: {len(sub)} rows, relevance agreement {agree}/{len(sub)} ({agree / len(sub):.0%})')
    print('   reference -> model:', dict(Counter((r['relevant'], r['pred_relevant']) for r in sub)))
    tp = sum(r['relevant'] == 'Sim' and r['pred_relevant'] == 'Sim' for r in sub)
    pp = sum(r['pred_relevant'] == 'Sim' for r in sub)
    ap = sum(r['relevant'] == 'Sim' for r in sub)
    print(f'   "Sim": model {pp}, reference {ap}, both {tp}')
    both = [r for r in sub if r['relevant'] == 'Sim' and r['pred_relevant'] == 'Sim']
    if both:
        print(f"   event type agreement on shared 'Sim': {sum(r['event_type'] == r['pred_event_type'] for r in both)}/{len(both)}")
    for r in sub:
        if r['relevant'] != r['pred_relevant']:
            print(f"   {r['id']} ref={r['relevant']} model={r['pred_relevant']} | {r['title'][:70]} | {r['pred_reason']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('reference')
    ap.add_argument('--model', default='gemma3:4b')
    ap.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    ap.add_argument('--batch', type=int, default=5)
    ap.add_argument('--pause', type=float, default=0, help='seconds between calls (hosted APIs)')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--out')
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    with open(args.reference, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    # Labels typed outside the dropdown during the first labeling round
    fix = {'Violência e segurança pública': 'Violência/operação policial',
           'Crise habitacional / favelas': 'Política habitacional'}
    for r in rows:
        r['event_type'] = fix.get(r['event_type'], r['event_type'])
    todo = rows[:args.limit] if args.limit else rows

    tokens_used = Counter()
    t0 = time.perf_counter()
    for i in range(0, len(todo), args.batch):
        batch = todo[i:i + args.batch]
        items, usage = call_model(args.endpoint, args.model, batch)
        tokens_used.update({k: v for k, v in usage.items() if isinstance(v, int)})
        by_id = {str(it.get('id')): it for it in items if isinstance(it, dict)}
        for j, r in enumerate(batch):
            # Fall back to position if the model rewrote the ids
            it = by_id.get(r['id']) or (items[j] if len(items) == len(batch) and isinstance(items[j], dict) else {})
            r['pred_relevant'] = RELEVANT.get(it.get('relevant'), 'Incerto')
            r['pred_event_type'] = EVENT_TYPES.get(it.get('event_type'), 'Outro')
            r['pred_reason'] = it.get('reason', '(sem resposta para este item)')
        done = min(i + args.batch, len(todo))
        print(f'   {done}/{len(todo)} classified ({(time.perf_counter() - t0) / done:.1f}s per item)', flush=True)
        if args.pause:
            time.sleep(args.pause)

    safe_model = re.sub(r'[^\w.-]+', '-', args.model.split('/')[-1])
    out = args.out or args.reference.replace('.csv', f'_pred_{safe_model}.csv')
    fields = list(rows[0].keys()) + [k for k in ('pred_relevant', 'pred_event_type', 'pred_reason') if k not in rows[0]]
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(todo)

    print(f'\nModel {args.model} | prompt {PROMPT_VERSION} | {len(todo)} items in '
          f'{time.perf_counter() - t0:.0f}s | tokens {dict(tokens_used)}')
    for source in ('human_blind', 'model_unreviewed'):
        report(todo, source)
    print(f'\nSaved {out}')


if __name__ == '__main__':
    main()
