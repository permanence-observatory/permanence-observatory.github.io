#!/usr/bin/env python3
"""
Build the data file for the new map (mapa/index.html) from the daily history.

Reads every data/gkg/YYYY/MM/YYYY-MM-DD.jsonl, keeps the stories the model
marked relevant or as a removal, and writes one point per story to
mapa/events.json. A story's place is chosen from, in order:
  1. a GKG location whose name contains the matched settlement name (settlement);
  2. the settlement's entry in the location dictionary (city: the dictionary
     mostly stores city coordinates);
  3. the first city GKG found in the text (city);
  4. the first state/province (region), then the first country (country).
Stories with no usable place are counted but not drawn. Each point is also tagged
Global North or South by its country (UN M49 developed regions = North).

Usage:
  python pipeline/build_map_data.py            # writes mapa/events.json
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'prototype'))
from gkg_prototype import RefinedSlumMapper, fold  # noqa: E402

# Event types of prompt 2026-11-02.1 (before topics) mapped to topics
OLD_TYPE_TOPICS = {
    'eviction': 'removal', 'demolition': 'removal', 'fire': 'disaster', 'flood_landslide': 'disaster',
    'violence_policing': 'violence', 'upgrading_infrastructure': 'infrastructure',
    'housing_policy': 'housing_policy', 'land_conflict': 'land_conflict', 'protest': 'protest',
    'health': 'health_education', 'other': 'other',
}
# Global North = the UN M49 "developed regions" (Europe, Northern America, Japan,
# Australia and New Zealand); every other country counts as Global South.
GLOBAL_NORTH = {fold(c) for c in (
    'United States', 'Canada', 'Greenland', 'Bermuda', 'Japan', 'Australia', 'New Zealand',
    'Albania', 'Andorra', 'Austria', 'Belarus', 'Belgium', 'Bosnia and Herzegovina', 'Bosnia-Herzegovina',
    'Bulgaria', 'Croatia', 'Czech Republic', 'Czechia', 'Denmark', 'Estonia', 'Faroe Islands', 'Finland',
    'France', 'Germany', 'Gibraltar', 'Greece', 'Hungary', 'Iceland', 'Ireland', 'Isle of Man', 'Italy',
    'Kosovo', 'Latvia', 'Liechtenstein', 'Lithuania', 'Luxembourg', 'Macedonia', 'North Macedonia', 'Malta',
    'Moldova', 'Monaco', 'Montenegro', 'Netherlands', 'Norway', 'Poland', 'Portugal', 'Romania', 'Russia',
    'San Marino', 'Serbia', 'Slovakia', 'Slovenia', 'Spain', 'Sweden', 'Switzerland', 'Ukraine',
    'United Kingdom', 'Vatican City', 'Jersey', 'Guernsey',
)}


def world_region(place_name):
    """'north' or 'south' from the country, the last part of the place name."""
    country = fold(place_name.split(',')[-1].strip())
    return 'north' if country in GLOBAL_NORTH else 'south'


CITY_TYPES = {'world_city', 'us_city'}
REGION_TYPES = {'world_adm1', 'us_state'}


def short_name(name):
    """'Usulutan, UsulutáEt, El Salvador' -> 'Usulutan, El Salvador'. GKG mangles the
    accents of the middle (state) part, so only the first and last parts are kept."""
    parts = [p.strip() for p in name.split(',') if p.strip()]
    return ', '.join([parts[0], parts[-1]]) if len(parts) > 2 else ', '.join(parts)


def place_for(group, db):
    names = [n for r in group for n in r.get('hit_name', [])]
    locations = [l for r in group for l in r.get('locations', [])]
    for n in names:
        for l in locations:
            if fold(n) in fold(l['name']) and l['type'] in CITY_TYPES:
                return l['lat'], l['lon'], short_name(l['name']), 'assentamento'
    for n in names:
        e = db.get(n)
        if e and e.get('lat') is not None:
            return e['lat'], e['lon'], f"{n.title()}, {e['city']}, {e['country']}", 'cidade'
    for kinds, precision in ((CITY_TYPES, 'cidade'), (REGION_TYPES, 'região'), ({'country'}, 'país')):
        for l in locations:
            if l['type'] in kinds:
                return l['lat'], l['lon'], short_name(l['name']), precision
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=os.path.join(ROOT, 'data', 'gkg'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'mapa', 'events.json'))
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    db = RefinedSlumMapper().location_db
    files = sorted(f for f in glob.glob(os.path.join(args.data, '*', '*', '*.jsonl')))
    events, skipped, days = [], Counter(), []
    for path in files:
        days.append(os.path.basename(path)[:10])
        stories = {}
        with open(path, encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                if r.get('relevant') == 'yes' or r.get('removal'):
                    stories.setdefault(r.get('story_id') or r['url'], []).append(r)
        for sid, g in stories.items():
            # The record with the most information represents the story
            face = next((r for r in g if r.get('removal')), g[0])
            place = place_for(g, db)
            if not place:
                skipped['no_place'] += 1
                continue
            lat, lon, place_name, precision = place
            topics = sorted({t for r in g for t in (r.get('topics') or [])})
            removal = face.get('removal')
            if not topics and 'event_type' in face:
                # classified before topics existed
                topics = [OLD_TYPE_TOPICS.get(face['event_type'], 'other')]
                if topics == ['removal']:
                    removal = 'unspecified'
            d = face['gkg_date']
            events.append({
                'id': sid, 'date': f'{d[:4]}-{d[4:6]}-{d[6:8]}',
                'title': face['title'] or '(sem título)', 'url': face['url'], 'source': face['source'],
                'lang': face['language'], 'reason': face.get('reason') or '',
                'topics': topics, 'removal': removal,
                'lat': round(lat, 4), 'lon': round(lon, 4), 'place': place_name, 'precision': precision,
                'region': world_region(place_name),
                'versions': len(g), 'prompt': face.get('prompt_version'),
            })

    events.sort(key=lambda e: (e['date'], e['id']), reverse=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out = {
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'days': days, 'events': events,
        'not_drawn': dict(skipped),
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f"{len(events)} stories from {len(days)} days -> {args.out} "
          f"({sum(skipped.values())} without a place; precision {dict(Counter(e['precision'] for e in events))})")


if __name__ == '__main__':
    main()
