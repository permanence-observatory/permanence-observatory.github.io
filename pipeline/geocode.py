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
The last part that names a country sets the country. The most general part left
is the context: a city, a state, or both. The more specific parts are looked up
inside it, first next to the city, then anywhere in the state. The result says
whether the point is a settlement or neighbourhood, a city, or only a region.

Usage (quick check):
  python pipeline/geocode.py "Chembur, Mumbai, India" "Kibos, Kisumu, Kenya"
"""

import io
import math
import os
import re
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
NEAR_KM = 60          # a place given with its city must lie this close to it
HINT_KM = 30          # ... or this close to the city GDELT found in the text
BIG_CITY = 100_000    # a lone name this big is read as the city, not the state
# Parts that name no place ("101 favelas and communities", "Colonias")
GENERIC_RE = re.compile(r'^\d|\b(favelas?|comunidades?|communities|colonias|settlements|slums|barrios|bairros|'
                        r'villages|asentamientos|neighbou?rhoods)\b')


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


def _rank(c):
    return CLASS_RANK.get(c[3], 9), -c[5]


def _feature_precision(c):
    """Precision from the GeoNames feature alone: a section of a town, a spot or an
    area is a settlement; a division or terrain is a region; any other place a city."""
    if c[3] in REGION_CLASSES:
        return 'região'
    if c[4] == 'PPLX' or c[3] in ('S', 'L'):
        return 'assentamento'
    return 'cidade'


def _hinted(c, name, near_hint):
    """'assentamento' when a place lies next to, but is not, the city GDELT found."""
    if (near_hint and c[3] not in REGION_CLASSES and _km(c[:2], near_hint[:2]) <= HINT_KM
            and fold(name) not in fold(near_hint[2]) and fold(near_hint[2]) not in fold(name)):
        return 'assentamento'
    return None


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
        # entry: (lat, lon, country, class, feature code, population, name, admin1 code)
        idx = {}
        for line in lines:
            p = line.split('\t')
            if len(p) < 15 or p[6] not in keep_classes:
                continue
            entry = (float(p[4]), float(p[5]), p[8], p[6], p[7], int(p[14] or 0), p[1], p[10])
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

    def _city(self, name, iso):
        """The most populous town of that name in the country, or None."""
        cands = [c for c in self._candidates(name, iso, local=False) if c[3] == 'P']
        return max(cands, key=lambda c: c[5]) if cands else None

    def _state(self, name, iso):
        """The first-level division (state, province) of that name, or None."""
        cands = [c for c in self._candidates(name, iso) if c[4] == 'ADM1']
        return cands[0] if cands else None

    def geocode(self, place, iso_hint=None, near_hint=None):
        """'Chembur, Mumbai, India' -> (lat, lon, label, precision) or None.

        precision is 'assentamento' for a place below the city (a neighbourhood or
        settlement), 'cidade' for a town or city, 'região' for a state or province.
        near_hint is (lat, lon, name) of the city GDELT found in the text; it settles
        lone names such as "Rocinha, Brazil"."""
        if not place or not place.strip():
            return None
        place = place.split(';')[0]   # several places: keep the first
        parts = [p.strip() for p in place.split(',') if p.strip()]
        iso = None
        for k in range(len(parts) - 1, -1, -1):   # the country: the last part that names one
            iso = self.country_code(parts[k])
            if iso:
                parts = parts[:k]
                break
        iso = iso or iso_hint
        parts = [p for p in parts if not GENERIC_RE.search(fold(p))]
        if not iso or not parts:
            return None
        country = self.country_names.get(iso, iso)
        if len(parts) == 1:
            return self._lone(parts[0], iso, country, near_hint)

        # The most general part is the context: a city, a state, or a name that is both
        ctx = parts[-1]
        city, state = self._city(ctx, iso), self._state(ctx, iso)
        if city and state and city[5] < BIG_CITY:
            city = None   # "Bahia", "Paraná": the state, not the small town of that name
        anchor = city
        if not city and not state:
            # an island, a county, a town spelled otherwise: any place of that name anchors the search
            others = self._candidates(ctx, iso)
            anchor = min(others, key=_rank) if others else None
        for i, name in enumerate(parts[:-1]):
            accepted = []
            for c in self._candidates(name, iso):
                if anchor and _km(c[:2], anchor[:2]) <= NEAR_KM:
                    accepted.append((c, 'near'))
                elif state and c[7] == state[7]:
                    accepted.append((c, 'state'))
            if accepted:
                c, how = min(accepted, key=lambda a: (a[1] != 'near', _rank(a[0])))
                if how == 'near' and city and c[3] not in REGION_CLASSES:
                    precision = 'assentamento'
                else:
                    precision = _hinted(c, name, near_hint) or _feature_precision(c)
                return c[0], c[1], f"{name}, {parts[i + 1]}, {country}", precision
        if city:
            return city[0], city[1], f"{ctx}, {country}", 'cidade'
        if state:
            return state[0], state[1], f"{ctx}, {country}", 'região'
        if anchor:
            return anchor[0], anchor[1], f"{ctx}, {country}", _feature_precision(anchor)
        return None

    def _lone(self, name, iso, country, near_hint):
        """A single name with its country: 'Rocinha, Brazil', 'Alagoas, Brazil'."""
        cands = self._candidates(name, iso)
        if not cands:
            return None
        label = f"{name}, {country}"
        city, state = self._city(name, iso), self._state(name, iso)
        if city and city[5] >= BIG_CITY:
            return city[0], city[1], label, 'cidade'
        if state:   # "Alagoas": the state, even if a farm near the story's city shares the name
            return state[0], state[1], label, 'região'
        if near_hint:
            close = [c for c in cands if _km(c[:2], near_hint[:2]) <= HINT_KM]
            if close:
                c = min(close, key=_rank)
                return c[0], c[1], label, _hinted(c, name, near_hint) or _feature_precision(c)
        if city:
            return city[0], city[1], label, 'cidade'
        c = min(cands, key=_rank)
        return c[0], c[1], label, _feature_precision(c)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    g = Geocoder()
    for p in sys.argv[1:]:
        print(p, '->', g.geocode(p))
