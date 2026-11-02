#!/usr/bin/env python3
"""
Build a spreadsheet for the team to label a sample of GKG candidates.

Reads a matches_*.jsonl written by gkg_prototype.py, re-applies the current
location check to settlement names, keeps languages the team can read and
draws a balanced sample across (criterion, language). The labeled sheet is
the reference set used to measure any filter or classifier.

Usage:
  python prototype/make_labeling_sheet.py prototype/output/matches_2026-11-02_every1.jsonl
"""

import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, os.path.dirname(__file__))
from gkg_prototype import RefinedSlumMapper, confirm_names  # noqa: E402

LANGUAGES = {'eng': 'Inglês', 'por': 'Português', 'spa': 'Espanhol', 'fra': 'Francês'}
CRITERIA = {'theme': 'Tema SLUMS do GKG', 'name': 'Nome de assentamento', 'keyword': 'Palavra-chave'}

LABEL_OPTIONS = {
    'Sobre assentamento informal?': ['Sim', 'Não', 'Incerto'],
    'Tipo de evento': [
        'Despejo/remoção', 'Demolição', 'Protesto', 'Incêndio', 'Enchente/deslizamento',
        'Conflito fundiário', 'Saúde/doença', 'Violência/operação policial',
        'Urbanização/infraestrutura', 'Política habitacional', 'Outro', 'Não se aplica',
    ],
    'Local correto?': ['Sim', 'Parcial', 'Não', 'Sem local'],
}
FREE_LABELS = ['Local real (se diferente)', 'Rotulado por', 'Observações']

FONT = 'Arial'
HEADER_FILL = PatternFill('solid', start_color='1F3A5F')
INPUT_FILL = PatternFill('solid', start_color='FFF2CC')


def primary_criterion(r):
    for key in ('theme', 'name', 'keyword'):
        if r[f'hit_{key}']:
            return key
    return None


def balanced_sample(records, size, seed):
    """Round-robin over (criterion, language) groups so small groups are represented."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for r in records:
        groups[(r['_criterion'], r['language'])].append(r)
    for g in groups.values():
        rng.shuffle(g)
    keys = sorted(groups)
    sample = []
    while len(sample) < size and any(groups[k] for k in keys):
        for k in keys:
            if groups[k] and len(sample) < size:
                sample.append(groups[k].pop())
    rng.shuffle(sample)
    return sample


def write_instructions(ws, source_file, counts):
    ws.title = 'Instruções'
    ws.column_dimensions['A'].width = 34
    ws.column_dimensions['B'].width = 95
    rows = [
        ('Planilha de rotulagem', ''),
        ('', ''),
        ('Objetivo', 'Criar um conjunto de referência para medir a qualidade da filtragem e da classificação '
                     'das notícias. Cada linha da aba "Rotulagem" é uma notícia que o filtro automático '
                     'considerou candidata.'),
        ('O que preencher', 'Apenas as colunas com fundo amarelo (J a O) da aba "Rotulagem". '
                            'Abra o link quando o título não for suficiente para decidir.'),
        ('Sobre assentamento informal?', 'Sim: a notícia trata de uma favela, assentamento informal, ocupação '
                                         'ou de seus moradores. Não: o termo aparece por outro motivo (nome de '
                                         'pessoa, time de futebol, bairro comum, sentido figurado). Incerto: '
                                         'não dá para decidir nem lendo a notícia.'),
        ('Tipo de evento', 'O assunto principal da notícia. Se não for sobre assentamento informal, use '
                           '"Não se aplica".'),
        ('Local correto?', 'Compare a coluna H (locais que o GDELT extraiu) com o local real da notícia. '
                           'Parcial: país ou cidade certos, mas não o assentamento. Se estiver errado, '
                           'escreva o local real na coluna M.'),
        ('Rotulado por', 'Suas iniciais, para sabermos quem rotulou cada linha.'),
        ('', ''),
        ('Exemplo de linha preenchida', ''),
        ('  Título', 'Residents of Kibera protest demolition of homes near railway line'),
        ('  Sobre assentamento informal?', 'Sim'),
        ('  Tipo de evento', 'Demolição'),
        ('  Local correto?', 'Parcial'),
        ('  Local real (se diferente)', 'Kibera, Nairobi, Quênia'),
        ('  Rotulado por', 'JP'),
        ('  Observações', 'Também menciona protesto; o assunto principal é a demolição'),
        ('', ''),
        ('Origem dos dados', f'{source_file}. Amostra equilibrada por critério e idioma, só idiomas que a '
                             'equipe lê (inglês, português, espanhol, francês). Títulos repetidos foram removidos.'),
        ('Composição da amostra', counts),
    ]
    for i, (a, b) in enumerate(rows, 1):
        ws.cell(i, 1, a).font = Font(name=FONT, bold=True, size=14 if i == 1 else 10)
        cell = ws.cell(i, 2, b)
        cell.font = Font(name=FONT, size=10)
        cell.alignment = Alignment(wrap_text=True, vertical='top')
        ws.cell(i, 1).alignment = Alignment(vertical='top')


def write_labels(ws, sample):
    ws.title = 'Rotulagem'
    info_cols = [
        ('ID', 7), ('Idioma', 11), ('Veículo', 22), ('Título', 60), ('Link', 30),
        ('Encontrada por', 20), ('Termos detectados', 22), ('Locais segundo o GDELT', 40),
        ('Data GDELT (UTC)', 16),
    ]
    label_cols = [(name, 18 if name in LABEL_OPTIONS else 26) for name in list(LABEL_OPTIONS) + FREE_LABELS]
    label_cols[1] = ('Tipo de evento', 26)
    headers = info_cols + label_cols

    for c, (name, width) in enumerate(headers, 1):
        cell = ws.cell(1, c, name)
        cell.font = Font(name=FONT, bold=True, color='FFFFFF')
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = 'E2'

    for i, r in enumerate(sample, 2):
        terms = r['hit_theme'] + r['hit_name'] + r['hit_keyword']
        places = '; '.join(l['name'] for l in r['locations'][:3])
        d = r['gkg_date']
        values = [
            f"R{i - 1:03d}", LANGUAGES[r['language']], r['source'], r['title'], r['url'],
            CRITERIA[r['_criterion']], ', '.join(terms), places,
            f"{d[:4]}-{d[4:6]}-{d[6:8]} {d[8:10]}:{d[10:12]}",
        ]
        for c, v in enumerate(values, 1):
            cell = ws.cell(i, c, v)
            cell.font = Font(name=FONT, size=10)
            cell.alignment = Alignment(wrap_text=c in (4, 8), vertical='top')
        link = ws.cell(i, 5)
        link.hyperlink = r['url']
        link.font = Font(name=FONT, size=10, color='0563C1', underline='single')
        for c in range(len(info_cols) + 1, len(headers) + 1):
            ws.cell(i, c).fill = INPUT_FILL
            ws.cell(i, c).font = Font(name=FONT, size=10)

    last = len(sample) + 1
    for offset, (name, options) in enumerate(LABEL_OPTIONS.items()):
        col = ws.cell(1, len(info_cols) + 1 + offset).column_letter
        dv = DataValidation(type='list', formula1='"' + ','.join(options) + '"', allow_blank=True)
        dv.error = 'Escolha uma opção da lista'
        ws.add_data_validation(dv)
        dv.add(f'{col}2:{col}{last}')
    ws.auto_filter.ref = f'A1:{ws.cell(1, len(headers)).column_letter}{last}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('matches')
    ap.add_argument('--size', type=int, default=200)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--out')
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    db = RefinedSlumMapper().location_db
    records, seen_titles = [], set()
    before = Counter()
    with open(args.matches, encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            # Older outputs stored unconfirmed names in hit_name
            raw = r.get('hit_name_raw', r['hit_name'])
            r['hit_name'] = confirm_names(raw, r['locations'], db)
            r['_criterion'] = primary_criterion(r)
            before['all'] += 1
            if not r['_criterion']:
                before['dropped_by_location_check'] += 1
                continue
            before['candidates'] += 1
            if r['language'] not in LANGUAGES:
                continue
            key = r['title'].strip().lower()
            if not key or key in seen_titles:
                continue
            seen_titles.add(key)
            records.append(r)

    sample = balanced_sample(records, args.size, args.seed)
    comp = Counter((CRITERIA[r['_criterion']], LANGUAGES[r['language']]) for r in sample)
    counts = '; '.join(f'{c} / {l}: {n}' for (c, l), n in sorted(comp.items()))

    wb = Workbook()
    write_instructions(wb.active, os.path.basename(args.matches), counts)
    write_labels(wb.create_sheet(), sample)
    out = args.out or os.path.join(os.path.dirname(args.matches),
                                   'rotulagem_' + os.path.basename(args.matches).split('_', 1)[1].split('_')[0] + '.xlsx')
    wb.save(out)

    print(f"Records in file: {before['all']}")
    print(f"Dropped by location check: {before['dropped_by_location_check']}")
    print(f"Candidates after check: {before['candidates']}")
    print(f"Candidates in eng/por/spa/fra, unique titles: {len(records)}")
    print(f"Sample written: {len(sample)} -> {out}")
    for (c, l), n in sorted(comp.items()):
        print(f"  {c:22} {l:10} {n}")


if __name__ == '__main__':
    main()
