#!/usr/bin/env python3
"""
Offline geocoder for the place names the model extracts from headlines.

Uses GeoNames (CC BY 4.0, https://www.geonames.org), downloaded once and cached
in .cache/geonames/:
  - countryInfo.txt   country names and codes;
  - cities500.zip     every town of 500+ people in the world (cities);
  - XX.zip            the full dump of one country, fetched only when a story from
                      that country needs a neighbourhood or settlement (these carry
                      neighbourhoods such as Tondo or Payatas that the cities file lacks).

A place string reads from specific to general, e.g. "Chembur, Mumbai, India".
The last part names the country; the geocoder tries the most specific part first,
inside that country, and when a city is also given it prefers the candidate
closest to that city. The result says whether the point is the settlement or
neighbourhood itself, or only the city.

Usage (quick check):
  python pipeline/geocode.py "Chembur, Mumbai, India" "Kibos, Kisumu, Kenya"
"""

import io
import math
import os
import sys
import urllib.request
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'prototype'))
from gkg_prototype import fold  # noqa: E402

BASE = 'https://download.geonames.org/export/dump/'
CACHE = os.path.join(ROOT, '.cache', 'geonames')

# Names the model or GKG use that GeoNames spells differently
COUNTRY_ALIASES = {
    'usa': 'US', 'united states of america': 'US', 'us': 'US', 'uk': 'GB', 'england': 'GB', 'scotland': 'GB',
    'wales': 'GB', 'great britain': 'GB', 'drc': 'CD', 'dr congo': 'CD', 'democratic republic of congo': 'CD',
    'democratic republic of the congo': 'CD', 'congo-kinshasa': 'CD', 'republic of the congo': 'CG',
    'congo-brazzaville': 'CG', 'ivory coast': 'CI', "cote d'ivoire": 'CI', 'south korea': 'KR', 'north korea': 'KP',
    'russia': 'RU', 'vietnam': 'VN', 'viet nam': 'VN', 'laos': 'LA', 'syria': 'SY', 'iran': 'IR', 'bolivia': 'BO',
    'venezuela': 'VE', 'tanzania': 'TZ', 'czech republic': 'CZ', 'palestine': 'PS', 'gaza': 'PS', 'west bank': 'PS',
    'macedonia': 'MK', 'burma': 'MM', 'eswatini': 'SZ', 'swaziland': 'SZ', 'cape verde': 'CV', 'brasil': 'BR',
    'mexico': 'MX', 'peru': 'PE', 'espana': 'ES', 'philippines': 'PH', 'the philippines': 'PH', 'india': 'IN',
    'puerto rico': 'PR', 'hong kong': 'HK', 'taiwan': 'TW', 'turkiye': 'TR', 'turkey': 'TR',
}
# Feature classes, best first: populated places, areas, spots (stations, schools),
# then islands and other terrain, then administrative divisions
CLASS_RANK = {'P': 0, 'L': 1, 'S': 2, 'T': 3, 'A': 4}
REGION_CLASSES = {'T', 'A'}


def _fetch(name):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        with urllib.request.urlopen(BASE + name, timeout=120) as r, open(path + '.part', 'wb') as f:
            f.write(r.read())
        os.replace(path + '.part', path)
    return path


def _read_zip(name, inner):
    with zipfile.ZipFile(_fetch(name)) as z:
        return io.TextIOWrapper(z.open(inner), encoding='utf-8').read().splitlines()


def _km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


class Geocoder:
    def __init__(self):
        self.countries = {}       # folded name -> ISO2
        self.country_names = {}   # ISO2 -> name
        self.fips = {}            # FIPS code (used by GDELT) -> ISO2
        for line in open(_fetch('countryInfo.txt'), encoding='utf-8'):
            if line.startswith('#') or not line.strip():
                continue
            p = line.rstrip('\n').split('\t')
            self.countries[fold(p[4])] = p[0]
            self.country_names[p[0]] = p[4]
            if p[3]:
                self.fips[p[3]] = p[0]
        self.countries.update(COUNTRY_ALIASES)
        self.cities = self._index(_read_zip('cities500.zip', 'cities500.txt'), alternates=False)
        self.by_country = {}

    @staticmethod
    def _index(lines, alternates=True, keep_classes=('P', 'L', 'S', 'T', 'A')):
        idx = {}
        for line in lines:
            p = line.split('\t')
            if len(p) < 15 or p[6] not in keep_classes:
                continue
            entry = (float(p[4]), float(p[5]), p[8], p[6], p[7], int(p[14] or 0), p[1])
            names = {fold(p[1]), fold(p[2])}
            if alternates and p[3]:
                names.update(fold(a) for a in p[3].split(',')[:30])
            for n in names:
                if n:
                    idx.setdefault((n, p[8]), []).append(entry)
        return idx

    def _country_index(self, iso):
        if iso not in self.by_country:
            try:
                self.by_country[iso] = self._index(_read_zip(f'{iso}.zip', f'{iso}.txt'))
            except Exception:  # network error or unknown code: fall back to the cities file
                self.by_country[iso] = {}
        return self.by_country[iso]

    def country_code(self, name):
        return self.countries.get(fold(name.strip()))

    def _candidates(self, name, iso, local=True):
        key = (fold(name.strip()), iso)
        found = list(self.cities.get(key, []))
        if local:
            found += self._country_index(iso).get(key, [])
        return found

    @staticmethod
    def _best(cands, near=None):
        if not cands:
            return None
        if near:
            close = [c for c in cands if _km(c[:2], near) <= 60]
            if close:
                return min(close, key=lambda c: (CLASS_RANK.get(c[3], 9), _km(c[:2], near)))
            return None
        return min(cands, key=lambda c: (CLASS_RANK.get(c[3], 9), -c[5]))

    def geocode(self, place, iso_hint=None):
        """'Chembur, Mumbai, India' -> (lat, lon, label, precision) or None.
        precision is 'assentamento' when the point is the specific place below the
        city, 'cidade' when only the city (or a single-name town) was found."""
        if not place or not place.strip():
            return None
        parts = [p.strip() for p in place.split(',') if p.strip()]
        iso = self.country_code(parts[-1]) if parts else None
        if iso:
            parts = parts[:-1]
        iso = iso or iso_hint
        if not iso or not parts:
            return None
        country = self.country_names.get(iso, iso)
        # The most general part below the country is usually the city
        city = self._best(self._candidates(parts[-1], iso, local=False)) if len(parts) >= 2 else None
        near = city[:2] if city else None
        for i, name in enumerate(parts):
            cand = self._best(self._candidates(name, iso), near if i < len(parts) - 1 else None)
            if cand:
                label = f"{name}, {parts[-1]}, {country}" if i < len(parts) - 1 else f"{name}, {country}"
                if cand[3] in REGION_CLASSES:
                    precision = 'região'
                elif i < len(parts) - 1 or (len(parts) == 1 and cand[4] in ('PPLX', 'AREA')):
                    precision = 'assentamento'
                else:
                    precision = 'cidade'
                return cand[0], cand[1], label, precision
        if city:
            return city[0], city[1], f"{parts[-1]}, {country}", 'cidade'
        return None


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    g = Geocoder()
    for p in sys.argv[1:]:
        print(p, '->', g.geocode(p))
