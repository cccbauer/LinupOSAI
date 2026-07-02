#!/usr/bin/env python3
"""
Dealer-run visualizer
=====================

Renders each croupier's draw sequence as an aligned, colour-coded grid so a
human can eyeball patterns before we try to model them. Every spin is one
column; each row is a different lens on that spin:

    #      spin index (1..n)
    Num    the drawn number, background = its roulette colour
    Col    roulette colour  R / B / G(reen)
    Doz    dozen            1 (1-12) / 2 (13-24) / 3 (25-36)
    Cln    column           I / II / III  (0 blank)
    L/H    low 1-18 / high 19-36
    E/O    even / odd
    Sect   wheel sector     Z0 / ZG / ZP / H

Reading top-to-bottom in one column tells you everything about that spin;
scanning a row left-to-right exposes rhythm in that one dimension.

Usage:  python3 ai_dealer_viz.py [datafile ...]   ->  writes dealer_viz.html
        (defaults to croupier_data.txt + ~/linup_data/croupier_log.txt)
Pure stdlib.
"""

import os
import sys
import webbrowser

from ai_combo_eval import ROJOS, SECTOR_OF
from ai_rhythm_eval import parse_file

# columns of the layout (every third number)
COLUMNS = {
    'I':   {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34},
    'II':  {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35},
    'III': {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36},
}

C_RED, C_BLACK, C_GREEN = '#c0392b', '#2c3e50', '#27ae60'
DOZ_BG = {1: '#8e44ad', 2: '#2980b9', 3: '#d35400'}
SECT_BG = {'Z0': '#16a085', 'ZG': '#c0392b', 'ZP': '#7f8c8d', 'H': '#f39c12'}


def color_of(n):
    if n == 0:
        return 'G'
    return 'R' if n in ROJOS else 'B'


def dozen_of(n):
    if n == 0:
        return None
    return (n - 1) // 12 + 1


def column_of(n):
    for name, s in COLUMNS.items():
        if n in s:
            return name
    return None


def cell(text, bg=None, fg='#eee', title=''):
    style = "border:1px solid #333;padding:2px 4px;text-align:center;" \
            "font:11px monospace;white-space:nowrap;"
    if bg:
        style += f"background:{bg};"
    style += f"color:{fg};"
    t = f' title="{title}"' if title else ''
    return f'<td style="{style}"{t}>{text}</td>'


def dealer_block(label, nums):
    cseq = [color_of(n) for n in nums]
    nR, nB, nG = cseq.count('R'), cseq.count('B'), cseq.count('G')
    dozc = {1: 0, 2: 0, 3: 0}
    for n in nums:
        d = dozen_of(n)
        if d:
            dozc[d] += 1
    stat = (f"{len(nums)} spins &nbsp;·&nbsp; "
            f"<span style='color:{C_RED}'>R {nR}</span> "
            f"<span style='color:#aaa'>B {nB}</span> "
            f"<span style='color:{C_GREEN}'>G {nG}</span> &nbsp;·&nbsp; "
            f"doz 1:{dozc[1]} 2:{dozc[2]} 3:{dozc[3]}")

    rows = {k: [] for k in ('#', 'Num', 'Col', 'Doz', 'Cln', 'L/H', 'E/O', 'Sect')}
    for i, n in enumerate(nums, 1):
        col = color_of(n)
        cbg = {'R': C_RED, 'B': C_BLACK, 'G': C_GREEN}[col]
        d = dozen_of(n)
        cln = column_of(n)
        lh = '' if n == 0 else ('L' if n <= 18 else 'H')
        eo = '' if n == 0 else ('E' if n % 2 == 0 else 'O')
        sect = SECTOR_OF.get(n, '')
        rows['#'].append(cell(i, '#111', '#666'))
        rows['Num'].append(cell(n, cbg, '#fff'))
        rows['Col'].append(cell(col, cbg, '#fff'))
        rows['Doz'].append(cell(d if d else '·', DOZ_BG.get(d), '#fff'))
        rows['Cln'].append(cell(cln or '·', '#222'))
        rows['L/H'].append(cell(lh or '·', '#222'))
        rows['E/O'].append(cell(eo or '·', '#222'))
        rows['Sect'].append(cell(sect or '·', SECT_BG.get(sect), '#fff'))

    trs = []
    for k in ('#', 'Num', 'Col', 'Doz', 'Cln', 'L/H', 'E/O', 'Sect'):
        head = (f'<td style="position:sticky;left:0;background:#000;color:#8af;'
                f'font:bold 11px monospace;padding:2px 6px;border:1px solid #333;">'
                f'{k}</td>')
        trs.append('<tr>' + head + ''.join(rows[k]) + '</tr>')

    return (f'<h3 style="color:#8af;margin:18px 0 4px;">{label}</h3>'
            f'<div style="color:#bbb;font:12px monospace;margin-bottom:4px;">{stat}</div>'
            f'<div style="overflow-x:auto;border:1px solid #222;">'
            f'<table style="border-collapse:collapse;">{"".join(trs)}</table></div>')


def build_html(dealers):
    legend = (
        '<div style="color:#bbb;font:12px monospace;margin:8px 0 16px;">'
        'Legend &nbsp; '
        f'<span style="background:{C_RED};color:#fff;padding:1px 5px;">R red</span> '
        f'<span style="background:{C_BLACK};color:#fff;padding:1px 5px;">B black</span> '
        f'<span style="background:{C_GREEN};color:#fff;padding:1px 5px;">G 0</span> &nbsp;|&nbsp; '
        f'<span style="background:{DOZ_BG[1]};color:#fff;padding:1px 5px;">doz1</span> '
        f'<span style="background:{DOZ_BG[2]};color:#fff;padding:1px 5px;">doz2</span> '
        f'<span style="background:{DOZ_BG[3]};color:#fff;padding:1px 5px;">doz3</span> &nbsp;|&nbsp; '
        f'<span style="background:{SECT_BG["Z0"]};color:#fff;padding:1px 5px;">Z0</span> '
        f'<span style="background:{SECT_BG["ZG"]};color:#fff;padding:1px 5px;">ZG</span> '
        f'<span style="background:{SECT_BG["ZP"]};color:#fff;padding:1px 5px;">ZP</span> '
        f'<span style="background:{SECT_BG["H"]};color:#fff;padding:1px 5px;">H</span>'
        '</div>')
    body = "".join(dealer_block(lbl, nums) for lbl, nums in dealers)
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<title>Dealer runs</title></head>'
            f'<body style="background:#0d0d0d;font-family:sans-serif;padding:16px;">'
            f'<h2 style="color:#eee;">Dealer runs — {len(dealers)} croupier(s)</h2>'
            f'{legend}{body}</body></html>')


def main():
    paths = sys.argv[1:] or [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "croupier_data.txt"),
        os.path.expanduser("~/linup_data/croupier_log.txt"),
    ]
    dealers = []
    for p in paths:
        if os.path.exists(p):
            dealers += parse_file(p)
    if not dealers:
        print("no dealer data found.")
        return
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dealer_viz.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_html(dealers))
    print(f"wrote {out}  ({len(dealers)} dealers)")
    try:
        webbrowser.open(f"file://{out}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
