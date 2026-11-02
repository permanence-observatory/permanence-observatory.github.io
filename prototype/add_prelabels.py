#!/usr/bin/env python3
"""
Add model-suggested labels to a labeling sheet, keeping a blind subset.

Every 4th row of the (already shuffled) sample goes to a blind sheet with no
suggestions, so the team's labels there can measure how often the model agrees
with people. The other rows get the suggestion pre-filled in the editable
columns, plus a read-only copy, so we can later see what reviewers changed.
Suggestions for blind rows are not written to the workbook.

Usage:
  python prototype/add_prelabels.py prototype/output/rotulagem_2026-11-02.xlsx \
      prototype/output/prelabels_2026-11-02.tsv
"""

import argparse
import csv
import os
import sys

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, os.path.dirname(__file__))
from make_labeling_sheet import FONT, FREE_LABELS, HEADER_FILL, INPUT_FILL, LABEL_OPTIONS  # noqa: E402

REL = {'S': 'Sim', 'N': 'Não', 'I': 'Incerto'}
LOCAL = {'S': 'Sim', 'P': 'Parcial', 'N': 'Não', 'X': 'Sem local'}
CONF = {'A': 'Alta', 'M': 'Média', 'B': 'Baixa'}
TIPO = {
    'NA': 'Não se aplica', 'DESP': 'Despejo/remoção', 'DEM': 'Demolição', 'PROT': 'Protesto',
    'INC': 'Incêndio', 'ENCH': 'Enchente/deslizamento', 'FUND': 'Conflito fundiário',
    'SAUDE': 'Saúde/doença', 'VIOL': 'Violência/operação policial',
    'URB': 'Urbanização/infraestrutura', 'HAB': 'Política habitacional', 'OUT': 'Outro',
}
SUGGESTION_COLS = [('Sugestão: assentamento?', 14), ('Sugestão: tipo', 22), ('Sugestão: local', 12),
                   ('Sugestão: confiança', 12), ('Justificativa da sugestão', 45)]
SUGGESTION_FILL = PatternFill('solid', start_color='E7E6E6')
INFO_COLS = 9


def read_suggestions(path):
    with open(path, encoding='utf-8') as f:
        lines = [l for l in f if not l.startswith('#')]
    out = {}
    for row in csv.DictReader(lines, delimiter='\t'):
        out[row['id']] = [REL[row['rel']], TIPO[row['tipo']], LOCAL[row['local']],
                          CONF[row['conf']], row['justificativa']]
    return out


def write_sheet(ws, header, widths, rows, label_start, suggestion_range=None):
    for c, (name, width) in enumerate(zip(header, widths), 1):
        cell = ws.cell(1, c, name)
        cell.font = Font(name=FONT, bold=True, color='FFFFFF')
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = 'E2'
    for i, (values, url) in enumerate(rows, 2):
        for c, v in enumerate(values, 1):
            cell = ws.cell(i, c, v)
            cell.font = Font(name=FONT, size=10)
            cell.alignment = Alignment(wrap_text=c in (4, 8) or header[c - 1].startswith('Justificativa'),
                                       vertical='top')
            if c >= label_start:
                cell.fill = INPUT_FILL
            elif suggestion_range and suggestion_range[0] <= c <= suggestion_range[1]:
                cell.fill = SUGGESTION_FILL
        link = ws.cell(i, 5)
        link.hyperlink = url
        link.font = Font(name=FONT, size=10, color='0563C1', underline='single')
    last = len(rows) + 1
    for offset, options in enumerate(LABEL_OPTIONS.values()):
        col = ws.cell(1, label_start + offset).column_letter
        dv = DataValidation(type='list', formula1='"' + ','.join(options) + '"', allow_blank=True)
        dv.error = 'Escolha uma opção da lista'
        ws.add_data_validation(dv)
        dv.add(f'{col}2:{col}{last}')
    ws.auto_filter.ref = f'A1:{ws.cell(1, len(header)).column_letter}{last}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sheet')
    ap.add_argument('suggestions')
    ap.add_argument('--blind-every', type=int, default=4)
    ap.add_argument('--out')
    args = ap.parse_args()

    src = load_workbook(args.sheet)
    base = src['Rotulagem']
    info_header = [base.cell(1, c).value for c in range(1, INFO_COLS + 1)]
    info_widths = [base.column_dimensions[base.cell(1, c).column_letter].width for c in range(1, INFO_COLS + 1)]
    label_names = list(LABEL_OPTIONS) + FREE_LABELS
    label_widths = [18, 26, 14, 26, 14, 30]
    suggestions = read_suggestions(args.suggestions)

    blind, review = [], []
    for i, r in enumerate(range(2, base.max_row + 1)):
        info = [base.cell(r, c).value for c in range(1, INFO_COLS + 1)]
        url = base.cell(r, 5).hyperlink.target
        if i % args.blind_every == 0:
            blind.append((info + [None] * len(label_names), url))
        else:
            s = suggestions[info[0]]
            prefill = [s[0], s[1], s[2], None, None, None]
            review.append((info + s + prefill, url))

    wb = Workbook()
    instr = wb.active
    instr.title = 'Instruções'
    old = src['Instruções']
    for row in old.iter_rows():
        for cell in row:
            new = instr.cell(cell.row, cell.column, cell.value)
            new.font = Font(name=FONT, bold=cell.font.bold, size=cell.font.size)
            new.alignment = Alignment(wrap_text=True, vertical='top')
    instr.column_dimensions['A'].width = 34
    instr.column_dimensions['B'].width = 95
    instr.cell(4, 2, 'Apenas as colunas com fundo amarelo. Abra o link quando o título não for suficiente para decidir.')
    extra = [
        ('', ''),
        ('Ordem de trabalho', '1) Aba "1. Cega": rotule do zero, sem consultar nenhuma sugestão. '
                              '2) Aba "2. Revisão": as colunas amarelas já vêm preenchidas com uma sugestão; '
                              'corrija o que discordar e escreva suas iniciais em "Rotulado por" para marcar a '
                              'linha como revisada, mesmo quando concordar com tudo.'),
        ('Por que uma aba cega', 'Para medir com números o quanto as sugestões concordam com a equipe. Se a '
                                 'aba cega for feita depois da revisão, ou olhando sugestões, a medida perde o valor.'),
        ('De onde vêm as sugestões', 'Geradas por um modelo de linguagem (Claude Opus 5.5, da Anthropic) em '
                                     '2026-11-02, lendo apenas título, link e locais do GDELT, sem abrir as '
                                     'matérias. As colunas cinzas guardam a sugestão original; não as edite.'),
    ]
    start = old.max_row + 1
    for k, (a, b) in enumerate(extra):
        instr.cell(start + k, 1, a).font = Font(name=FONT, bold=True, size=10)
        cell = instr.cell(start + k, 2, b)
        cell.font = Font(name=FONT, size=10)
        cell.alignment = Alignment(wrap_text=True, vertical='top')

    write_sheet(wb.create_sheet('1. Cega (fazer primeiro)'), info_header + label_names,
                info_widths + label_widths, blind, INFO_COLS + 1)
    sug_names = [n for n, _ in SUGGESTION_COLS]
    sug_widths = [w for _, w in SUGGESTION_COLS]
    write_sheet(wb.create_sheet('2. Revisão'), info_header + sug_names + label_names,
                info_widths + sug_widths + label_widths, review,
                INFO_COLS + len(SUGGESTION_COLS) + 1,
                (INFO_COLS + 1, INFO_COLS + len(SUGGESTION_COLS)))

    out = args.out or args.sheet.replace('.xlsx', '_v2.xlsx')
    wb.save(out)
    print(f"Blind rows: {len(blind)} | review rows with suggestions: {len(review)} -> {out}")


if __name__ == '__main__':
    main()
