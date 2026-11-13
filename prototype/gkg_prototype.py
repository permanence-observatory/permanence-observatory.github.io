#!/usr/bin/env python3
"""
Prototype: collect informal-settlement news from GDELT GKG raw files.

Instead of ~300 calls to the rate-limited DOC API, this downloads the
15-minute GKG files for one UTC day (English feed + translated feed for
65 languages) and filters every record locally. It does not touch the
production pipeline; it only writes results to --out.

A record is kept when any of these match:
  - theme:   a GKG theme in TARGET_THEMES (e.g. SLUMS)
  - name:    a settlement name from the current location database
  - keyword: a multilingual keyword from the current script
  - removal: a removal word (eviction, desalojo, despejo, déguerpissement...)
             together with a housing word (homes, families, ocupação, viviendas...),
             so eviction stories reach the classifier even without "slum" or "favela"
Names, keywords and removal words are searched in the page title and URL;
names also in GKG's extracted proper names and locations.

Usage:
  python prototype/gkg_prototype.py --date 2026-11-01 --every 8   # sample
  python prototype/gkg_prototype.py --date 2026-11-01             # full day
"""

import argparse
import html
import io
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from gdelt_version_v21 import RefinedSlumMapper  # noqa: E402

BASE = 'http://data.gdeltproject.org/gdeltv2'
FEEDS = {
    'en': '{ts}.gkg.csv.zip',
    'translation': '{ts}.translation.gkg.csv.zip',
}
TARGET_THEMES = {'SLUMS'}

# GKG 2.1 column positions
C_ID, C_DATE, C_SOURCE, C_URL = 0, 1, 3, 4
C_THEMES, C_LOCATIONS, C_ALLNAMES, C_TRANSLATION, C_EXTRAS = 7, 9, 23, 25, 26

LOCATION_TYPES = {'1': 'country', '2': 'us_state', '3': 'us_city', '4': 'world_city', '5': 'world_adm1'}
TITLE_RE = re.compile(r'<PAGE_TITLE>(.*?)</PAGE_TITLE>', re.S)

# How GKG may spell countries that the location database names differently
COUNTRY_ALIASES = {'DRC': ['Congo'], 'Ivory Coast': ["Cote d'Ivoire", 'Ivory Coast']}

# Settlement names that are also common words, person names or whole districts.
# Initial list from the 2026-11-02 sample; these also need the city to match.
AMBIGUOUS_NAMES = {
    'alexandra', 'medina', 'bello', 'sadar', 'jamestown', 'langa', 'el alto',
    'masina', 'basti', 'jhuggi', 'matonge', 'comas', 'badia', 'yeka', 'uttara',
    'mirpur', 'mohammadpur', 'soacha', 'agege', 'mushin', 'bariga',
}


# Removal words, matched on accent-free lowercase title + URL words.
# Strong words almost always mean removal of homes; weak ones also mean
# "evacuate" or "clear a road" in Spanish, so they need more evidence.
STRONG_REMOVAL_RE = re.compile(
    r'\b(evict\w*|demoli\w*|bulldoz\w*|razed|desmantel\w*|despejos?|despejad[ao]s?|'
    r'remoc\w*|reintegracao de posse|deguerpi\w*|demantel\w*)\b')
WEAK_REMOVAL_RE = re.compile(r'\b(desaloj\w*|despej\w*)\b')
# Housing or occupation words that make a removal word about people's homes
HOUSING_RE = re.compile(
    r'\b(casas?|moradias?|moradores?|familias|ocupac\w*|ocupantes?|invasao|invasoes|assentamentos?|barracos?|'
    r'viviendas?|asentamientos?|campamentos?|tomas? de (?:tierras?|terrenos?)|colonias?|'
    r'residents?|families|homes?|houses?|housing|settlements?|settlers?|squatt\w*|shacks?|dwellers?|slums?|hutments?|'
    r'logements?|familles|habitants?|maisons?|bidonvilles?|occupants?|informal\w*)\b')


def removal_entry(text_folded):
    """Removal words in a text that also talks about homes, or [] (entry criterion)."""
    words = set(STRONG_REMOVAL_RE.findall(text_folded)) | set(WEAK_REMOVAL_RE.findall(text_folded))
    return sorted(words) if words and HOUSING_RE.search(text_folded) else []


def fold(text):
    """Lowercase and strip accents, so 'Bogotá' matches 'Bogota'."""
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


def confirm_names(hit_names, locations, location_db):
    """Keep a settlement name only if GKG located the article in the same country
    (and, for ambiguous names, the same city)."""
    places = fold(' | '.join(l['name'] for l in locations))
    confirmed = []
    for name in hit_names:
        entry = location_db.get(name)
        if not entry:
            continue
        countries = [entry['country']] + COUNTRY_ALIASES.get(entry['country'], [])
        if not any(fold(c) in places for c in countries):
            continue
        if name in AMBIGUOUS_NAMES and fold(entry['city']) not in places:
            continue
        confirmed.append(name)
    return confirmed


def build_matcher(terms):
    """One compiled regex for a list of phrases, matching whole words only."""
    alts = sorted({t.lower() for t in terms}, key=len, reverse=True)
    pattern = r'(?<!\w)(' + '|'.join(re.escape(t) for t in alts) + r')(?!\w)'
    return re.compile(pattern, re.I)


def timestamps(day, every):
    start = datetime.strptime(day, '%Y-%m-%d')
    slots = [start + timedelta(minutes=15 * i) for i in range(96)]
    return [s.strftime('%Y%m%d%H%M%S') for s in slots[::every]]


def download(url, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(3 * (attempt + 1))
    return None


def parse_locations(field):
    out = []
    for loc in field.split(';'):
        p = loc.split('#')
        if len(p) >= 7 and p[4] and p[5]:
            out.append({'type': LOCATION_TYPES.get(p[0], p[0]), 'name': p[1],
                        'country_code': p[2], 'lat': float(p[4]), 'lon': float(p[5])})
    return out


def url_text(url):
    """Turn a URL path into words: /news/kibera-eviction-2026 -> 'news kibera eviction 2026'."""
    path = url.split('://', 1)[-1].split('/', 1)[-1]
    return re.sub(r'[\W_]+', ' ', path)


# GKG themes about housing, land and displacement; records with them that miss the
# pre-filter are the "near misses" the funnel audit samples
NEAR_MISS_THEMES = {
    'WB_817_LAND_AND_HOUSING', 'WB_2186_SOCIAL_HOUSING', 'WB_1722_HOUSING_POLICY_AND_INSTITUTIONS',
    'WB_888_LAND_TENURE', 'WB_964_PROPERTY_AND_LAND_LAW', 'WB_891_LAND_REFORM', 'EVICTION',
}
# Settlement and occupation words that, unlike "house" or "home", rarely mean something else
SETTLEMENT_WORD_RE = re.compile(
    r'\b(moradias? precarias?|ocupac\w* (?:irregular\w*|ilega\w*|urbana\w*)|ocupacoes urbanas|ocupantes?|barracos?|'
    r'comunidades? carentes?|viviendas? (?:precarias?|irregulares?|informales?)|infraviviendas?|'
    r'asentamientos?|campamentos?|tomas? de (?:tierras?|terrenos?)|colonias? (?:populares?|irregulares?)|'
    r'informal settlements?|squatt\w*|shacks?|slum dwellers?|hutments?|shanty\w*|'
    r'logements? (?:sociaux|insalubres?)|bidonvilles?|quartiers? precaires?)\b')


class GkgCounter:
    """Counts every GKG row seen (the denominator for the candidates): total, by feed,
    by source language and by country. The English feed counts as 'eng'; in the
    translation feed the language is the srclc code of the translation field. The
    country is the first country code among the V2 locations ('none' when absent;
    GKG uses FIPS codes, e.g. BR, IN, US)."""

    def __init__(self):
        self.total = 0
        self.by_feed, self.by_language, self.by_country = Counter(), Counter(), Counter()

    def add(self, feed, row):
        self.total += 1
        self.by_feed[feed] += 1
        if feed == 'en':
            lang = 'eng'
        else:
            lang = row[C_TRANSLATION].split(';')[0].replace('srclc:', '') or 'unknown'
        self.by_language[lang] += 1
        first = row[C_LOCATIONS].split(';', 1)[0].split('#')
        self.by_country[first[2] if len(first) > 2 and first[2] else 'none'] += 1

    def result(self):
        ordered = lambda c: dict(c.most_common())  # noqa: E731
        return {'total': self.total, 'by_feed': ordered(self.by_feed),
                'by_language': ordered(self.by_language), 'by_country': ordered(self.by_country)}


def collect(day, every=1, feeds=('en', 'translation'), workers=4, mapper=None, near_miss=False):
    """Download one UTC day of GKG files and return (matches, stats, counters, all_urls).
    With near_miss=True, counters['near_miss'] also lists records that did NOT pass the
    pre-filter but carry a housing/land theme or a settlement/occupation word in the title."""
    mapper = mapper or RefinedSlumMapper()
    slum_names = [n for n, d in mapper.location_db.items() if d['type'] == 'slum']
    keywords = [k for lang in mapper.slum_keywords.values() for k in lang]
    name_re = build_matcher(slum_names)
    kw_re = build_matcher(keywords)

    jobs = [(feed, ts, f"{BASE}/{FEEDS[feed].format(ts=ts)}")
            for ts in timestamps(day, every) for feed in feeds]
    print(f"{len(jobs)} files to fetch ({day}, 1 in {every} slots, feeds={list(feeds)})")

    stats = Counter()
    gkg_counter = GkgCounter()
    term_hits, co_themes, langs, loc_types = Counter(), Counter(), Counter(), Counter()
    all_urls, matches, near = set(), {}, {}
    t0 = time.perf_counter()
    parse_time = 0.0

    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(download, url): (feed, ts) for feed, ts, url in jobs}
        for n, fut in enumerate(as_completed(futures), 1):
            feed, ts = futures[fut]
            content = fut.result()
            if content is None:
                stats['files_missing'] += 1
                continue
            stats['files_ok'] += 1
            stats['bytes'] += len(content)
            tp = time.perf_counter()
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                text = z.read(z.namelist()[0]).decode('utf-8', 'replace')
            for line in text.split('\n'):
                row = line.split('\t')
                if len(row) < 27:
                    continue
                stats[f'records_{feed}'] += 1
                gkg_counter.add(feed, row)
                url = row[C_URL]
                all_urls.add(url)
                if url in matches:
                    continue
                m = TITLE_RE.search(row[C_EXTRAS])
                title = html.unescape(m.group(1)).strip() if m else ''
                themes = set(t for t in row[C_THEMES].split(';') if t)
                locations = parse_locations(row[C_LOCATIONS])
                loc_names = ' | '.join(l['name'] for l in locations)
                title_url = f"{title} {url_text(url)}"

                hit_theme = sorted(themes & TARGET_THEMES)
                hit_name = sorted({x.lower() for x in name_re.findall(f"{title_url} {row[C_ALLNAMES]} {loc_names}")})
                hit_kw = sorted({x.lower() for x in kw_re.findall(title_url)})
                name_ok = confirm_names(hit_name, locations, mapper.location_db)
                if hit_name and not name_ok:
                    stats['names_rejected_by_location'] += 1
                hit_removal = removal_entry(fold(title_url))
                if not (hit_theme or name_ok or hit_kw or hit_removal):
                    if near_miss and title and url not in near and len(near) < 50000 and (
                            themes & NEAR_MISS_THEMES or any('EVICT' in t for t in themes)
                            or SETTLEMENT_WORD_RE.search(fold(title_url))):
                        lang = row[C_TRANSLATION].split(';')[0].replace('srclc:', '') if row[C_TRANSLATION] else 'eng'
                        near[url] = {'url': url, 'source': row[C_SOURCE], 'gkg_date': row[C_DATE], 'language': lang,
                                     'title': title, 'locations': locations[:5],
                                     'themes': sorted(themes & NEAR_MISS_THEMES)}
                    continue
                if hit_removal and not (hit_theme or name_ok or hit_kw):
                    stats['entered_by_removal_only'] += 1

                lang = row[C_TRANSLATION].split(';')[0].replace('srclc:', '') if row[C_TRANSLATION] else 'eng'
                matches[url] = {
                    'url': url, 'source': row[C_SOURCE], 'gkg_date': row[C_DATE], 'feed': feed,
                    'language': lang, 'title': title,
                    'hit_theme': hit_theme, 'hit_name': name_ok, 'hit_name_raw': hit_name,
                    'hit_keyword': hit_kw, 'hit_removal': hit_removal,
                    'locations': locations[:10],
                    'themes': sorted(themes),
                }
                langs[lang] += 1
                for t in name_ok:
                    term_hits[('name', t)] += 1
                for t in hit_kw:
                    term_hits[('keyword', t)] += 1
                co_themes.update(themes)
                loc_types.update({l['type'] for l in locations} or {'none'})
            parse_time += time.perf_counter() - tp
            if n % 10 == 0:
                print(f"  {n}/{len(jobs)} files, {len(matches)} matches so far", flush=True)

    stats['seconds_total'] = time.perf_counter() - t0
    stats['seconds_parsing'] = parse_time
    gkg_articles = {**gkg_counter.result(), 'unique_urls': len(all_urls)}
    counters = {'gkg_articles': gkg_articles, 'term_hits': term_hits, 'co_themes': co_themes, 'langs': langs, 'loc_types': loc_types,
                'near_miss': [r for u, r in near.items() if u not in matches]}
    return list(matches.values()), stats, counters, all_urls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True, help='UTC day, YYYY-MM-DD')
    ap.add_argument('--every', type=int, default=1, help='use 1 of every N 15-min files (sampling)')
    ap.add_argument('--feeds', default='en,translation')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--out', default=os.path.join(os.path.dirname(__file__), 'output'))
    ap.add_argument('--compare', default=os.path.join(os.path.dirname(__file__), '..', 'index.html'),
                    help='published map to compare against')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # titles come in many scripts

    feeds = args.feeds.split(',')
    m, stats, counters, all_urls = collect(args.date, args.every, feeds, args.workers)
    matches = {r['url']: r for r in m}
    term_hits, co_themes = counters['term_hits'], counters['co_themes']
    langs, loc_types = counters['langs'], counters['loc_types']
    total, parse_time = stats['seconds_total'], stats['seconds_parsing']
    by = Counter()
    for r in m:
        key = '+'.join(k for k in ('theme', 'name', 'keyword', 'removal') if r.get(f'hit_{k}'))
        by[key] += 1

    # Compare with the published map (same calendar day only)
    comparison = None
    if os.path.exists(args.compare):
        with open(args.compare, encoding='utf-8') as f:
            page = f.read()
        js = re.search(r'const eventsData = (\[.*?\]);\n', page, re.S)
        if js:
            events = json.loads(js.group(1))
            same_day = [e for e in events if str(e.get('date', '')).startswith(args.date)]
            urls = {e['url'] for e in same_day}
            comparison = {
                'map_events_total': len(events),
                'map_events_same_day': len(same_day),
                'same_day_found_in_gkg_files': len(urls & all_urls),
                'same_day_kept_by_gkg_filter': len(urls & set(matches)),
                'note': 'GKG coverage depends on --every; with sampling most map URLs will be missing',
            }

    summary = {
        'date': args.date, 'every': args.every, 'feeds': feeds,
        'files_ok': stats['files_ok'], 'files_missing': stats['files_missing'],
        'downloaded_mb': round(stats['bytes'] / 1e6, 1),
        'seconds_total': round(total, 1), 'seconds_parsing': round(parse_time, 1),
        'records_en': stats['records_en'], 'records_translation': stats['records_translation'],
        'unique_urls_seen': len(all_urls),
        'matches': len(m), 'matches_by_criterion': dict(by.most_common()),
        'records_whose_names_were_all_rejected': stats['names_rejected_by_location'],
        'entered_by_removal_only': stats['entered_by_removal_only'],
        'languages': dict(langs.most_common(15)),
        'location_types_in_matches': dict(loc_types.most_common()),
        'top_terms': [f"{k}:{t} = {c}" for (k, t), c in term_hits.most_common(40)],
        'top_cooccurring_themes': dict(co_themes.most_common(40)),
        'comparison_with_published_map': comparison,
    }

    tag = f"{args.date}_every{args.every}"
    with open(os.path.join(args.out, f'matches_{tag}.jsonl'), 'w', encoding='utf-8') as f:
        for r in m:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    with open(os.path.join(args.out, f'summary_{tag}.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps({k: v for k, v in summary.items() if k != 'top_cooccurring_themes'}, indent=2, ensure_ascii=False))
    print(f"\nSaved to {args.out}")


if __name__ == '__main__':
    main()
