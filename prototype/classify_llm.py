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
PROMPT_VERSION = '2026-11-10.1'

# Topics; a story can have several. Removal is the observatory's priority.
TOPICS = {
    'removal': 'Remoção/demolição', 'disaster': 'Desastre (incêndio, enchente, deslizamento)',
    'violence': 'Violência e segurança', 'housing_policy': 'Política habitacional e regularização',
    'infrastructure': 'Urbanização e infraestrutura', 'land_conflict': 'Conflito fundiário e ocupação',
    'protest': 'Protesto e organização comunitária', 'culture': 'Cultura e pessoas',
    'economy': 'Economia e trabalho', 'health_education': 'Saúde e educação',
    'data': 'Estudos e dados', 'other': 'Outro',
}
# Stage of a removal story
REMOVAL_STAGES = {
    'executed': 'Executada', 'threat': 'Ameaça ou anúncio', 'court': 'Decisão judicial',
    'resettlement': 'Reassentamento', 'unspecified': 'Etapa não identificada',
}
RELEVANT = {'yes': 'Sim', 'no': 'Não', 'uncertain': 'Incerto'}

SYSTEM_PROMPT = f"""You screen news headlines for an observatory of informal settlements
(slums, favelas, shantytowns, squatter or irregular settlements, villas miseria, barriadas,
asentamientos, bidonvilles, katchi abadis, South African informal settlements). It collects
any relevant news about them, and above all news about removals of their homes.

For each item decide:
relevant:
  "yes" if the article gives relevant information about informal settlements or their
        residents, on ANY topic: removals, fires, floods, crime or police action inside them,
        housing policy, services, culture, people who live or grew up there, studies and data,
        or a policy that mentions them.
  "no"  only if the matching word is a coincidence: a person, band or brand name, a sports
        club, a US or planned "township", a generic "community", an ordinary neighbourhood
        called "barriada", or another unrelated meaning of the word.
  "uncertain" only when the headline genuinely cannot be decided either way.
topics: one or more of {', '.join(TOPICS)}. Use [] when relevant is "no".
removal: "none" unless the article is about removing homes in an informal settlement. Then:
  "executed" (demolition or eviction happened), "threat" (announced, planned, notices served),
  "court" (a court authorizes or blocks it), "resettlement" (families moved or rehoused).
  When removal is not "none", topics must include "removal".
reason: at most 15 words, in Portuguese, only when relevant is "yes" or "uncertain"; else "".

Headlines can be in any language. Use the URL words and the GDELT locations as extra clues,
but GDELT locations are often wrong. Answer only with JSON:
{{"items": [{{"id": "...", "relevant": "...", "topics": ["..."], "removal": "...", "reason": "..."}}]}}"""


def normalize_answer(a):
    """Make one model answer consistent: known codes only, removal implies the topic."""
    relevant = a.get('relevant') if a.get('relevant') in RELEVANT else 'uncertain'
    topics = a.get('topics') if isinstance(a.get('topics'), list) else [a.get('topics')]
    topics = [t for t in topics if t in TOPICS]
    removal = a.get('removal') if a.get('removal') in REMOVAL_STAGES else None
    if removal and 'removal' not in topics:
        topics.insert(0, 'removal')
    if 'removal' in topics and not removal:
        removal = 'unspecified'
    if relevant == 'no':
        topics, removal = [], None
    elif not topics:
        topics = ['other']
    return {'relevant': relevant, 'topics': topics, 'removal': removal, 'reason': a.get('reason') or ''}


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
            a = normalize_answer(it)
            r['pred_relevant'] = RELEVANT[a['relevant']]
            r['pred_topics'] = '; '.join(TOPICS[t] for t in a['topics'])
            r['pred_removal'] = REMOVAL_STAGES.get(a['removal'], '')
            r['pred_reason'] = a['reason'] if it else '(sem resposta para este item)'
        done = min(i + args.batch, len(todo))
        print(f'   {done}/{len(todo)} classified ({(time.perf_counter() - t0) / done:.1f}s per item)', flush=True)
        if args.pause:
            time.sleep(args.pause)

    safe_model = re.sub(r'[^\w.-]+', '-', args.model.split('/')[-1])
    out = args.out or args.reference.replace('.csv', f'_pred_{safe_model}.csv')
    fields = list(rows[0].keys()) + [k for k in ('pred_relevant', 'pred_topics', 'pred_removal', 'pred_reason')
                                     if k not in rows[0]]
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
