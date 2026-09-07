#!/usr/bin/env python3
"""
DB ER Skill — Interactive ER Diagram Generator
Generates a self-contained HTML ER diagram from a database.
Supports MySQL, PostgreSQL, SQL Server, and SQLite.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse


# ── Schema fetchers ────────────────────────────────────────────────────────────

def fetch_mysql(dsn: str, tables: list[str], exclude: list[str]) -> dict:
    try:
        import pymysql
    except ImportError:
        sys.exit("pymysql not installed. Run: pip install pymysql")

    p = urlparse(dsn)
    conn = pymysql.connect(
        host=p.hostname, port=p.port or 3306,
        user=p.username, password=p.password,
        database=p.path.lstrip('/'),
        charset='utf8mb4', connect_timeout=10,
    )
    cur = conn.cursor()

    cur.execute("""
        SELECT TABLE_NAME, TABLE_COMMENT
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME
    """, (p.path.lstrip('/'),))
    table_comments = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("""
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY, IS_NULLABLE, COLUMN_COMMENT
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME, ORDINAL_POSITION
    """, (p.path.lstrip('/'),))
    rows = cur.fetchall()
    conn.close()

    return _build_schema(rows, table_comments, tables, exclude, col_idx=(0,1,2,3,5))


def fetch_postgres(dsn: str, tables: list[str], exclude: list[str]) -> dict:
    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2 not installed. Run: pip install psycopg2-binary")

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    cur.execute("""
        SELECT c.table_name,
               col.column_name,
               col.udt_name,
               CASE WHEN pk.column_name IS NOT NULL THEN 'PRI'
                    WHEN uk.column_name IS NOT NULL THEN 'UNI'
                    WHEN idx.column_name IS NOT NULL THEN 'MUL'
                    ELSE '' END AS key,
               col.is_nullable,
               COALESCE(pgd.description, '') AS comment
        FROM information_schema.columns col
        JOIN information_schema.tables c
          ON c.table_name = col.table_name AND c.table_schema = col.table_schema
        LEFT JOIN pg_catalog.pg_statio_all_tables st
          ON st.relname = col.table_name AND st.schemaname = col.table_schema
        LEFT JOIN pg_catalog.pg_description pgd
          ON pgd.objoid = st.relid AND pgd.objsubid = col.ordinal_position
        LEFT JOIN (
            SELECT ku.table_name, ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku
              ON tc.constraint_name = ku.constraint_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
        ) pk ON pk.table_name = col.table_name AND pk.column_name = col.column_name
        LEFT JOIN (
            SELECT ku.table_name, ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku
              ON tc.constraint_name = ku.constraint_name
            WHERE tc.constraint_type = 'UNIQUE'
        ) uk ON uk.table_name = col.table_name AND uk.column_name = col.column_name
        LEFT JOIN (
            SELECT i.relname, a.attname AS column_name, t.relname AS table_name
            FROM pg_index ix JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        ) idx ON idx.table_name = col.table_name AND idx.column_name = col.column_name
        WHERE col.table_schema = 'public'
        ORDER BY col.table_name, col.ordinal_position
    """)
    rows = cur.fetchall()

    cur.execute("""
        SELECT relname, obj_description(oid) FROM pg_class
        WHERE relkind = 'r' AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname='public')
    """)
    table_comments = {r[0]: r[1] or '' for r in cur.fetchall()}
    conn.close()

    return _build_schema(rows, table_comments, tables, exclude, col_idx=(0,1,2,3,5))


def fetch_sqlserver(dsn: str, tables: list[str], exclude: list[str]) -> dict:
    try:
        import pymssql
    except ImportError:
        sys.exit("pymssql not installed. Run: pip install pymssql")

    p = urlparse(dsn)
    conn = pymssql.connect(
        server=p.hostname, port=p.port or 1433,
        user=p.username, password=p.password,
        database=p.path.lstrip('/'),
    )
    cur = conn.cursor()

    cur.execute("""
        SELECT t.name,
               ep.value
        FROM sys.tables t
        LEFT JOIN sys.extended_properties ep
          ON ep.major_id = t.object_id AND ep.minor_id = 0 AND ep.name = 'MS_Description'
        ORDER BY t.name
    """)
    table_comments = {r[0]: r[1] or '' for r in cur.fetchall()}

    cur.execute("""
        SELECT
            t.name AS table_name,
            c.name AS column_name,
            tp.name AS type_name,
            CASE WHEN pk.column_id IS NOT NULL THEN 'PRI'
                 WHEN uk.column_id IS NOT NULL THEN 'UNI'
                 WHEN ix.column_id IS NOT NULL THEN 'MUL'
                 ELSE '' END AS key,
            CASE WHEN c.is_nullable = 1 THEN 'YES' ELSE 'NO' END,
            ISNULL(CAST(ep.value AS NVARCHAR(500)), '') AS comment
        FROM sys.columns c
        JOIN sys.tables t ON t.object_id = c.object_id
        JOIN sys.types tp ON tp.user_type_id = c.user_type_id
        LEFT JOIN sys.extended_properties ep
          ON ep.major_id = c.object_id AND ep.minor_id = c.column_id AND ep.name = 'MS_Description'
        LEFT JOIN (
            SELECT ic.object_id, ic.column_id FROM sys.index_columns ic
            JOIN sys.indexes i ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            WHERE i.is_primary_key = 1
        ) pk ON pk.object_id = c.object_id AND pk.column_id = c.column_id
        LEFT JOIN (
            SELECT ic.object_id, ic.column_id FROM sys.index_columns ic
            JOIN sys.indexes i ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            WHERE i.is_unique = 1 AND i.is_primary_key = 0
        ) uk ON uk.object_id = c.object_id AND uk.column_id = c.column_id
        LEFT JOIN (
            SELECT ic.object_id, ic.column_id FROM sys.index_columns ic
            JOIN sys.indexes i ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            WHERE i.is_unique = 0
        ) ix ON ix.object_id = c.object_id AND ix.column_id = c.column_id
        ORDER BY t.name, c.column_id
    """)
    rows = cur.fetchall()
    conn.close()

    return _build_schema(rows, table_comments, tables, exclude, col_idx=(0,1,2,3,5))


def fetch_sqlite(dsn: str, tables: list[str], exclude: list[str]) -> dict:
    import sqlite3
    path = dsn.replace('sqlite:///', '').replace('sqlite://', '')
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    all_tables = [r[0] for r in cur.fetchall()]
    table_comments = {t: '' for t in all_tables}

    rows = []
    for tname in all_tables:
        cur.execute(f"PRAGMA table_info({tname})")
        for col in cur.fetchall():
            # cid, name, type, notnull, dflt_value, pk
            key = 'PRI' if col[5] else ''
            rows.append((tname, col[1], col[2], key, 'YES' if not col[3] else 'NO', ''))
    conn.close()

    return _build_schema(rows, table_comments, tables, exclude, col_idx=(0,1,2,3,5))


def _build_schema(rows, table_comments, whitelist, blacklist, col_idx):
    ti, ci, tyi, ki, cmi = col_idx
    schema = {}
    for row in rows:
        tname = row[ti]
        if whitelist and tname not in whitelist:
            continue
        if tname in blacklist:
            continue
        if tname not in schema:
            schema[tname] = {
                'comment': (table_comments.get(tname) or '')[:40],
                'cols': []
            }
        schema[tname]['cols'].append({
            'key': row[ki] or '',
            'col': row[ci],
            'type': (row[tyi] or '').split('(')[0],
            'cmt': (row[cmi] or '')[:40],
        })
    return schema


# ── Relationship inference ─────────────────────────────────────────────────────

def infer_relations(schema: dict, no_infer: bool = False) -> list[dict]:
    """
    Infer table relationships by:
    1. Explicit foreign keys (COLUMN_KEY='MUL' with _id suffix pointing to another table)
    2. Field name → table name matching (user_id → users.id)
    3. Same-name PK/UK fields shared across tables
    """
    tables = set(schema.keys())
    rels = []
    seen = set()

    def add_rel(src, sf, tgt, tf, desc):
        key = (src, tgt, sf, tf)
        if key not in seen:
            seen.add(key)
            rels.append({'s': src, 'sf': sf, 't': tgt, 'tf': tf, 'desc': desc})

    for tname, info in schema.items():
        for col in info['cols']:
            cname = col['col'].lower()
            cmt   = col['cmt']

            # ── Rule 1: explicit FK annotation in comment (→ table.col) ──────
            m = re.search(r'→\s*(\w+)\.(\w+)', cmt)
            if m:
                tgt, tf = m.group(1), m.group(2)
                if tgt in tables:
                    add_rel(tname, col['col'], tgt, tf, f'{col["col"]}→{tf}')
                    continue

            if no_infer:
                continue

            # ── Rule 2: _id suffix → table PK ─────────────────────────────────
            if cname.endswith('_id') and col['key'] != 'PRI':
                base = cname[:-3]  # strip _id
                # Try exact match, then plural/singular variants
                candidates = [base, base + 's', base.rstrip('s')]
                for cand in candidates:
                    # Case-insensitive table lookup
                    match = next((t for t in tables if t.lower() == cand or
                                  t.lower() == cand.rstrip('_') or
                                  t.lower().endswith('_' + cand)), None)
                    if match and match != tname:
                        # Find PK of target table
                        pks = [c['col'] for c in schema[match]['cols'] if c['key'] == 'PRI']
                        tf = pks[0] if pks else 'id'
                        add_rel(tname, col['col'], match, tf,
                                f'{col["col"]} → {match}.{tf}')
                        break

            # ── Rule 3: fk_ prefix ─────────────────────────────────────────────
            elif cname.startswith('fk_') and col['key'] != 'PRI':
                base = cname[3:]
                for cand in [base, base + 's']:
                    match = next((t for t in tables if t.lower() == cand), None)
                    if match and match != tname:
                        pks = [c['col'] for c in schema[match]['cols'] if c['key'] == 'PRI']
                        tf = pks[0] if pks else 'id'
                        add_rel(tname, col['col'], match, tf,
                                f'{col["col"]} → {match}.{tf}')
                        break

    # ── Rule 4: shared non-trivial same-name fields between tables ─────────────
    if not no_infer:
        field_tables = defaultdict(list)
        for tname, info in schema.items():
            for col in info['cols']:
                if col['key'] in ('PRI', 'UNI') and col['col'].lower() not in ('id', 'wid'):
                    field_tables[col['col'].lower()].append((tname, col['col']))

        for fname, owners in field_tables.items():
            if len(owners) < 2:
                continue
            # Connect all pairs (up to 3 to avoid noise)
            for i, (t1, c1) in enumerate(owners[:3]):
                for t2, c2 in owners[i+1:4]:
                    if t1 != t2:
                        add_rel(t1, c1, t2, c2, f'共享字段 {c1}')

    return rels


# ── Grouping ───────────────────────────────────────────────────────────────────

# Default grouping rules: prefix → (label, color, bg)
DEFAULT_GROUP_RULES = [
    # (prefix_list, label, color, bg)
    (['sys_', 'system_'],    '系统表',   '#475569', '#f1f5f9'),
    (['log_', 'audit_'],     '日志/审计', '#b91c1c', '#fee2e2'),
    (['dict_', 'code_'],     '字典/编码', '#0e7490', '#cffafe'),
    (['user', 'account', 'auth', 'role', 'perm'],
                             '用户/权限', '#7c3aed', '#ede9fe'),
    (['order', 'trade', 'pay', 'bill'],
                             '交易/订单', '#b45309', '#fff7ed'),
    (['product', 'goods', 'sku', 'category'],
                             '商品/分类', '#15803d', '#dcfce7'),
    (['student', 'stu', 'xs', 'xj', 'xjgl'],
                             '学籍/学生', '#1d4ed8', '#dbeafe'),
    (['teacher', 'jzg', 'ds_', 't_ds', 't_jzg'],
                             '教职工',   '#7c3aed', '#ede9fe'),
    (['course', 'kc', 'kcgl', 'lesson'],
                             '课程',     '#b45309', '#fff7ed'),
    (['grade', 'score', 'cj', 'exam'],
                             '成绩/考试', '#15803d', '#dcfce7'),
]

FALLBACK_COLORS = [
    ('#1d4ed8', '#dbeafe'),
    ('#15803d', '#dcfce7'),
    ('#7c3aed', '#ede9fe'),
    ('#0e7490', '#cffafe'),
    ('#b45309', '#fff7ed'),
    ('#b91c1c', '#fee2e2'),
    ('#475569', '#f1f5f9'),
]


def assign_groups(schema: dict) -> dict[str, dict]:
    """Assign each table to a group based on name prefix heuristics."""
    groups: dict[str, dict] = {}
    group_order: list[str] = []

    def get_or_create_group(label: str, color: str, bg: str) -> str:
        if label not in groups:
            groups[label] = {
                'label': label, 'color': color, 'bg': bg, 'tables': []
            }
            group_order.append(label)
        return label

    for tname in sorted(schema.keys()):
        assigned = False
        tl = tname.lower()
        for prefixes, label, color, bg in DEFAULT_GROUP_RULES:
            if any(tl.startswith(p) or p in tl for p in prefixes):
                grp = get_or_create_group(label, color, bg)
                groups[grp]['tables'].append(tname)
                assigned = True
                break
        if not assigned:
            grp = get_or_create_group('其他', '#475569', '#f1f5f9')
            groups[grp]['tables'].append(tname)

    return {k: groups[k] for k in group_order if groups[k]['tables']}


# ── Layout ─────────────────────────────────────────────────────────────────────

ROW_H = 22
HDR_H = 46
TBL_W = 244
COL_GAP = 24
GRP_GAP = 48
GRP_PAD = 14
GRP_COLS = 3


def compute_layout(schema: dict, groups: dict, fold_n: int = 10):
    """Compute pixel positions for each table card."""
    def tbl_h(tname):
        return HDR_H + min(len(schema[tname]['cols']), fold_n) * ROW_H

    def layout_group(tables, gx, gy):
        nc = 2 if len(tables) > 3 else 1
        cw = TBL_W + COL_GAP
        cy = [gy + GRP_PAD] * nc
        pos = {}
        for t in tables:
            i = cy.index(min(cy))
            pos[t] = (gx + GRP_PAD + i * cw, cy[i])
            cy[i] += tbl_h(t) + COL_GAP
        gw = GRP_PAD * 2 + nc * cw - COL_GAP
        gh = max(cy) - gy + GRP_PAD
        return pos, gw, gh

    gy = [20] * GRP_COLS
    result = []
    for i, (glabel, ginfo) in enumerate(groups.items()):
        col = i % GRP_COLS
        gx = col * (2 * (TBL_W + COL_GAP) + 2 * GRP_PAD + GRP_GAP)
        pos, gw, gh = layout_group(ginfo['tables'], gx, gy[col])
        result.append({
            **ginfo,
            'x': gx, 'y': gy[col], 'w': gw, 'h': gh,
            'cx': gx + gw // 2, 'cy': gy[col] + gh // 2,
            'pos': pos,
        })
        gy[col] += gh + GRP_GAP

    canvas_w = max(g['x'] + g['w'] for g in result) + 80
    canvas_h = max(g['y'] + g['h'] for g in result) + 80
    return result, canvas_w, canvas_h


# ── JS data serialisation ──────────────────────────────────────────────────────

def esc(s: str) -> str:
    return (s or '')[:35].replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')


def build_js_data(schema, groups_layout, rels, fold_n):
    # Nodes
    nodes = []
    for g in groups_layout:
        for tname in g['tables']:
            if tname not in schema:
                continue
            info = schema[tname]
            tx, ty = g['pos'][tname]
            degree = sum(1 for r in rels if r['s'] == tname or r['t'] == tname)
            sym = max(16, min(50, 16 + degree * 2))
            col_data = [
                '{"k":"%s","n":"%s","t":"%s","c":"%s"}' % (
                    c['key'], c['col'],
                    c['type'].split('(')[0], esc(c['cmt'])
                )
                for c in info['cols']
            ]
            nodes.append(
                '{"id":"%s","grp":"%s","sub":"%s","x":%d,"y":%d,'
                '"hd":"%s","hdbg":"%s","bdc":"%s",'
                '"colCount":%d,"symbolSize":%d,"degree":%d,'
                '"itemStyle":{"color":"%s","borderColor":"%s","borderWidth":2},'
                '"label":{"show":true,"color":"%s","fontSize":12,"fontWeight":"bold","formatter":"{b}"},'
                '"colData":[%s]}' % (
                    tname, g['label'], esc(info['comment']), tx, ty,
                    g['color'], g['bg'], g['color'],
                    len(info['cols']), sym, degree,
                    g['bg'], g['color'],
                    g['color'],
                    ','.join(col_data),
                )
            )

    # Edges (merge multiple rels between same pair)
    edge_map = {}
    for r in rels:
        key = (r['s'], r['t'])
        rkey = (r['t'], r['s'])
        if key not in edge_map and rkey not in edge_map:
            edge_map[key] = []
        if key in edge_map:
            edge_map[key].append(r)
        else:
            edge_map[rkey].append(r)

    edges = []
    for (src, tgt), rs in edge_map.items():
        pairs = ','.join(
            '{"sf":"%s","tf":"%s","desc":"%s"}' % (esc(r['sf']), esc(r['tf']), esc(r['desc']))
            for r in rs
        )
        edges.append(
            '{"source":"%s","target":"%s","pairs":[%s],'
            '"lineStyle":{"width":1.5,"curveness":0.12,"color":"#475569","opacity":0.6}}'
            % (src, tgt, pairs)
        )

    # Groups
    cat_names = list({g['label'] for g in groups_layout})
    grp_js = []
    for g in groups_layout:
        grp_js.append(
            '{"id":"%s","label":"%s","x":%d,"y":%d,"w":%d,"h":%d,'
            '"hd":"%s","hdbg":"%s","bdc":"%s","cx":%d,"cy":%d}' % (
                g['label'].replace('"', '\\"'), g['label'].replace('"', '\\"'),
                g['x'], g['y'], g['w'], g['h'],
                g['color'], g['bg'], g['color'],
                g['cx'], g['cy'],
            )
        )

    cats = '[' + ','.join('{"name":"%s"}' % n.replace('"', '\\"') for n in cat_names) + ']'

    return (
        'const NODES=[\n' + ',\n'.join(nodes) + '\n];\n'
        'const EDGES=[\n' + ',\n'.join(edges) + '\n];\n'
        'const GROUPS=[\n' + ',\n'.join(grp_js) + '\n];\n'
        'const CATS=' + cats + ';\n'
    )


# ── HTML template ──────────────────────────────────────────────────────────────

def build_html(title: str, data_js: str, theme: str, font_size: int, fold_n: int,
               canvas_w: int, canvas_h: int) -> str:
    fs = font_size
    fs_sm = fs - 2
    fs_xs = fs - 4
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme}">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
:root{{
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:Consolas,"Cascadia Code",monospace;
  --r:5px;
  --fs:{fs}px;--fs-sm:{fs_sm}px;--fs-xs:{fs_xs}px;
}}
[data-theme="dark"]{{
  --bg:#0f172a;--surf:#1e293b;--surf2:#263347;--bd:#334155;
  --text:#e2e8f0;--muted:#94a3b8;--dim:#64748b;
  --acc:#818cf8;--acc-bg:#312e81;--acc-t:#c7d2fe;
  --ntc:#93c5fd;--lc:#475569;--ec:#818cf8;
  --ttbg:#1e293b;--ttbd:#334155;--tttext:#e2e8f0;
  --ac:#86efac;--hib:rgba(99,102,241,.32);--hit:#c7d2fe;
  --smc:#86efac;--cbg:#0f172a;--even:#172033;
}}
[data-theme="light"]{{
  --bg:#f8fafc;--surf:#ffffff;--surf2:#f1f5f9;--bd:#e2e8f0;
  --text:#0f172a;--muted:#475569;--dim:#94a3b8;
  --acc:#4f46e5;--acc-bg:#ede9fe;--acc-t:#3730a3;
  --ntc:#1d4ed8;--lc:#94a3b8;--ec:#4f46e5;
  --ttbg:#ffffff;--ttbd:#e2e8f0;--tttext:#0f172a;
  --ac:#15803d;--hib:rgba(79,70,229,.15);--hit:#3730a3;
  --smc:#15803d;--cbg:#f8fafc;--even:#f8fafc;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);font-family:var(--font);font-size:var(--fs);color:var(--text);
  height:100vh;display:flex;flex-direction:column;overflow:hidden;
  transition:background .18s,color .18s}}
#bar{{flex-shrink:0;height:48px;background:var(--surf);border-bottom:1px solid var(--bd);
  display:flex;align-items:center;gap:7px;padding:0 14px;z-index:30;
  user-select:none;transition:background .18s,border-color .18s}}
#bar h1{{font-size:var(--fs-sm);font-weight:700;color:var(--text);white-space:nowrap;flex-shrink:0}}
.sp{{width:1px;height:22px;background:var(--bd);flex-shrink:0}}
.btn{{padding:4px 11px;border:1px solid var(--bd);border-radius:var(--r);background:var(--surf);
  cursor:pointer;font-size:var(--fs-sm);color:var(--muted);white-space:nowrap;
  transition:all .1s;line-height:1.4}}
.btn:hover{{background:var(--surf2);color:var(--text)}}
.btn.on{{background:var(--acc-bg);border-color:var(--acc);color:var(--acc-t)}}
#sw{{position:relative;flex:0 0 210px}}
#sw svg{{position:absolute;left:8px;top:50%;transform:translateY(-50%);
  color:var(--dim);pointer-events:none}}
#search{{width:100%;padding:5px 26px 5px 26px;border:1px solid var(--bd);border-radius:var(--r);
  font-size:var(--fs-sm);background:var(--bg);color:var(--text);outline:none;
  transition:border-color .15s,background .18s}}
#search:focus{{border-color:var(--acc);background:var(--surf)}}
#sc{{position:absolute;right:7px;top:50%;transform:translateY(-50%);
  font-size:var(--fs-xs);color:var(--dim)}}
.lg{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-left:auto}}
.li{{display:flex;align-items:center;gap:3px;font-size:var(--fs-xs);color:var(--muted);
  cursor:pointer;padding:2px 5px;border-radius:3px;white-space:nowrap;transition:background .1s}}
.li:hover{{background:var(--surf2)}}.li.off{{opacity:.25}}
.ld{{width:8px;height:8px;border-radius:2px;flex-shrink:0}}
#sr{{position:absolute;top:48px;left:0;right:0;max-height:340px;background:var(--surf);
  border-bottom:1px solid var(--bd);overflow-y:auto;z-index:40;display:none;
  box-shadow:0 8px 24px rgba(0,0,0,.18);transition:background .18s}}
.sr-row{{padding:7px 12px;border-bottom:1px solid var(--bd);cursor:pointer;
  display:flex;flex-direction:column;gap:2px}}
.sr-row:hover{{background:var(--surf2)}}
.sr-tn{{font-family:var(--mono);font-size:var(--fs-sm);font-weight:600;color:var(--ntc)}}
.sr-sub{{font-size:var(--fs-xs);color:var(--dim)}}
.sr-col{{font-size:var(--fs-xs);color:var(--smc);font-family:var(--mono)}}
.hi{{background:var(--hib);border-radius:2px;color:var(--hit)}}
#layout{{flex:1;display:flex;overflow:hidden}}
#sb{{flex-shrink:0;width:210px;background:var(--surf);border-right:1px solid var(--bd);
  display:flex;flex-direction:column;overflow:hidden;
  transition:width .15s,background .18s,border-color .18s}}
#sb.hide{{width:0;border-right:none;overflow:hidden}}
#sb-top{{padding:8px 8px 6px;border-bottom:1px solid var(--bd);flex-shrink:0}}
#sb-q{{width:100%;padding:4px 7px;border:1px solid var(--bd);border-radius:var(--r);
  background:var(--bg);color:var(--text);font-size:var(--fs-sm);outline:none;
  transition:border-color .15s,background .18s}}
#sb-q:focus{{border-color:var(--acc)}}
#sb-body{{flex:1;overflow-y:auto;padding:4px 0}}
.sg{{margin-bottom:1px}}
.sg-hd{{padding:5px 8px 3px;font-size:var(--fs-xs);font-weight:700;color:var(--dim);
  text-transform:uppercase;letter-spacing:.06em;cursor:pointer;
  display:flex;align-items:center;gap:5px;user-select:none}}
.sg-hd:hover{{color:var(--muted)}}
.sg-hd .gdot{{width:7px;height:7px;border-radius:2px;flex-shrink:0}}
.sg-hd .ga{{font-size:9px;opacity:.6;margin-left:auto;transition:transform .12s}}
.sg-hd.col .ga{{transform:rotate(-90deg)}}
.sg-items.hide{{display:none}}
.st{{padding:3px 8px 3px 18px;cursor:pointer;display:flex;flex-direction:column;
  gap:1px;border-radius:var(--r);margin:0 3px;transition:background .08s}}
.st:hover{{background:var(--surf2)}}.st.active{{background:var(--acc-bg)}}
.st-n{{font-family:var(--mono);font-size:var(--fs-xs);color:var(--ntc);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.st.active .st-n{{color:var(--acc-t)}}
.st-s{{font-size:10px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
#chart{{flex:1;min-width:0}}
#det{{flex-shrink:0;width:300px;background:var(--surf);border-left:1px solid var(--bd);
  display:flex;flex-direction:column;overflow:hidden;
  transition:width .15s,background .18s,border-color .18s}}
#det.hide{{width:0;border-left:none;overflow:hidden}}
#dh{{padding:10px 12px 8px;border-bottom:1px solid var(--bd);flex-shrink:0}}
#dh h2{{font-family:var(--mono);font-size:var(--fs-sm);font-weight:700;color:var(--text);
  word-break:break-all;margin-bottom:2px}}
.d-sub{{font-size:var(--fs-sm);color:var(--muted);margin-bottom:5px}}
.d-meta{{font-size:var(--fs-xs);color:var(--dim);display:flex;gap:8px;flex-wrap:wrap}}
.d-x{{float:right;cursor:pointer;color:var(--dim);font-size:14px;line-height:1}}
.d-x:hover{{color:var(--text)}}
.tabs{{display:flex;border-bottom:1px solid var(--bd);flex-shrink:0}}
.tab{{flex:1;padding:6px 0;text-align:center;font-size:var(--fs-sm);cursor:pointer;
  color:var(--dim);border-bottom:2px solid transparent;transition:all .1s}}
.tab:hover{{color:var(--muted)}}.tab.on{{color:var(--acc);border-bottom-color:var(--acc)}}
#tf{{display:none;flex-direction:column;overflow-y:auto;flex:1}}
#tf.show{{display:flex}}
.fr{{display:flex;align-items:baseline;padding:3px 10px;
  border-bottom:1px solid var(--bd);gap:5px;font-size:var(--fs-sm)}}
.fr:nth-child(even){{background:var(--even)}}
.fr:hover{{background:var(--surf2)}}
.fr.mf{{background:var(--hib)!important}}
.fk{{font-size:10px;font-weight:700;padding:1px 3px;border-radius:2px;flex-shrink:0}}
.fpk{{background:#fef3c7;color:#92400e}}
.fuk{{background:#f0fdf4;color:#15803d}}
.fix{{background:#f5f3ff;color:#6d28d9}}
.fn{{font-family:var(--mono);color:var(--ntc);flex:0 0 110px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.ft{{color:var(--dim);flex:0 0 60px;font-size:var(--fs-xs)}}
.fc{{color:var(--muted);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
#tr{{display:none;flex-direction:column;overflow-y:auto;flex:1;padding:6px 0}}
#tr.show{{display:flex}}
.ri{{padding:5px 10px;border-bottom:1px solid var(--bd)}}
.ri:last-child{{border-bottom:none}}
.ra{{color:var(--acc);font-weight:700;margin-right:3px}}
.rt{{color:var(--ntc);font-family:var(--mono);font-size:var(--fs-sm)}}
.rd{{color:var(--dim);font-size:var(--fs-xs);margin-top:1px}}
.rf{{font-size:var(--fs-xs);color:var(--dim);font-family:var(--mono)}}
</style>
</head>
<body>
<div id="bar">
  <h1>{title}</h1>
  <div class="sp"></div>
  <div id="sw">
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
      <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" stroke-width="1.5"/>
      <path d="M10 10l4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
    <input id="search" type="text" placeholder="搜索表名 / 字段 / 注释…" autocomplete="off"/>
    <span id="sc"></span>
  </div>
  <button class="btn on"  id="btn-sb"     onclick="toggleSb()">隐藏列表</button>
  <button class="btn on"  id="btn-labels" onclick="toggleLabels()">隐藏标签</button>
  <button class="btn"     id="btn-nm"     onclick="toggleNM()">显示中文名</button>
  <button class="btn"     onclick="resetView()">重置布局</button>
  <button class="btn"     id="btn-theme"  onclick="toggleTheme()">{"☀ 亮色模式" if theme=="dark" else "🌙 暗色模式"}</button>
  <div class="sp"></div>
  <div class="lg" id="legend"></div>
</div>
<div style="position:relative;z-index:35"><div id="sr"></div></div>
<div id="layout">
  <div id="sb">
    <div id="sb-top">
      <input id="sb-q" type="text" placeholder="过滤表名 / 注释…" autocomplete="off"/>
    </div>
    <div id="sb-body"></div>
  </div>
  <div id="chart"></div>
  <div id="det" class="hide">
    <div id="dh">
      <span class="d-x" onclick="closeDet()">✕</span>
      <h2 id="d-name"></h2>
      <div class="d-sub" id="d-sub"></div>
      <div class="d-meta" id="d-meta"></div>
    </div>
    <div class="tabs">
      <div class="tab on" id="tab-tf" onclick="showTab('f')">字段</div>
      <div class="tab"    id="tab-tr" onclick="showTab('r')">关联</div>
    </div>
    <div id="tf"></div>
    <div id="tr"></div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<script>
{data_js}
const CANVAS_W={canvas_w};const CANVAS_H={canvas_h};const FOLD_N={fold_n};
// ── adjacency ──────────────────────────────────────────────────────────────
const adjOut={{}},adjIn={{}};
NODES.forEach(n=>{{adjOut[n.id]=[];adjIn[n.id]=[];}});
EDGES.forEach(e=>{{adjOut[e.source]?.push(e);adjIn[e.target]?.push(e);}});
// ── state ──────────────────────────────────────────────────────────────────
const hiddenGrps=new Set();
let showLabels=true,nameMode='en',darkMode={'true' if theme=='dark' else 'false'},activeId=null;
let pendingId=null,mdX=0,mdY=0;
// ── chart ──────────────────────────────────────────────────────────────────
let chart=initChart();
function initChart(){{
  const c=echarts.init(document.getElementById('chart'),darkMode?'dark':'light',{{renderer:'canvas'}});
  c.on('mousedown',{{dataType:'node'}},p=>{{pendingId=p.data.id;mdX=p.event.offsetX;mdY=p.event.offsetY;}});
  c.getZr().on('mouseup',e=>{{
    if(!pendingId)return;
    const dx=e.offsetX-mdX,dy=e.offsetY-mdY;
    if(Math.sqrt(dx*dx+dy*dy)<8)openDet(pendingId);
    pendingId=null;
  }});
  c.getZr().on('click',e=>{{if(!e.target)closeDet();}});
  return c;
}}
window.addEventListener('resize',()=>chart.resize());
const css=p=>getComputedStyle(document.documentElement).getPropertyValue(p).trim();
function nodeName(n){{return nameMode==='cn'?(n.sub||n.id):n.id;}}
function buildOption(){{
  const vis=new Set(NODES.filter(n=>!hiddenGrps.has(n.grp)).map(n=>n.id));
  const ns=NODES.filter(n=>vis.has(n.id)).map(n=>({{
    ...n,name:nodeName(n),
    label:{{...n.label,show:showLabels,fontSize:nameMode==='cn'?11:12,fontWeight:'bold',color:n.itemStyle.borderColor}},
  }}));
  const lc=css('--lc'),ec=css('--ec');
  const es=EDGES.filter(e=>vis.has(e.source)&&vis.has(e.target)).map(e=>
    ({{...e,lineStyle:{{...e.lineStyle,color:lc}},emphasis:{{lineStyle:{{color:ec,width:2.5,opacity:1}}}}}}));
  const ntc=css('--ntc'),mc=css('--muted'),dc=css('--dim'),ac=css('--ac');
  return {{
    backgroundColor:css('--cbg'),
    tooltip:{{
      trigger:'item',backgroundColor:css('--ttbg'),borderColor:css('--ttbd'),
      padding:[7,11],textStyle:{{color:css('--tttext'),fontSize:13}},
      formatter(p){{
        if(p.dataType==='node'){{
          const n=p.data,deg=(adjOut[n.id]?.length||0)+(adjIn[n.id]?.length||0);
          return `<b style="font-family:monospace;color:${{ntc}}">${{n.id}}</b><br/>
            <span style="color:${{mc}}">${{n.sub}}</span><br/>
            <span style="color:${{dc}}">${{n.colCount}}列 · ${{deg}}条关联</span>`;
        }}
        if(p.dataType==='edge'){{
          const lines=p.data.pairs.map(p2=>
            `<span style="font-family:monospace;color:${{ac}}">${{p2.sf}}</span> → <span style="font-family:monospace;color:${{ac}}">${{p2.tf}}</span>  <span style="color:${{dc}}">${{p2.desc}}</span>`
          ).join('<br/>');
          return `<b style="color:${{ntc}}">${{p.data.source}}</b><br/><b style="color:${{ntc}}">${{p.data.target}}</b><br/>${{lines}}`;
        }}
        return '';
      }}
    }},
    series:[{{
      type:'graph',layout:'force',data:ns,links:es,categories:CATS,
      roam:true,draggable:true,focusNodeAdjacency:true,
      force:{{repulsion:340,gravity:0.05,edgeLength:[80,230],friction:0.55}},
      lineStyle:{{curveness:0.12}},
      emphasis:{{focus:'adjacency',label:{{show:true}}}},
      blur:{{itemStyle:{{opacity:.1}},lineStyle:{{opacity:.04}}}},
    }}]
  }};
}}
chart.setOption(buildOption());
// ── detail ──────────────────────────────────────────────────────────────────
function badge(k){{
  if(k==='PRI')return'<span class="fk fpk">PK</span>';
  if(k==='UNI')return'<span class="fk fuk">UK</span>';
  if(k==='MUL')return'<span class="fk fix">IX</span>';
  return'';
}}
function openDet(id,hiCol){{
  const n=NODES.find(x=>x.id===id);if(!n)return;
  activeId=id;
  document.getElementById('d-name').textContent=n.id;
  document.getElementById('d-sub').textContent=n.sub;
  const outC=adjOut[id]?.length||0,inC=adjIn[id]?.length||0;
  document.getElementById('d-meta').innerHTML=`<span>${{n.colCount}}列</span><span>→${{outC}}个关联</span><span>←${{inC}}个引用</span>`;
  const tf=document.getElementById('tf');
  tf.innerHTML=n.colData.map(c=>{{
    const hi=hiCol&&(c.n.toLowerCase().includes(hiCol)||c.c.toLowerCase().includes(hiCol))?' mf':'';
    return`<div class="fr${{hi}}">${{badge(c.k)}}<span class="fn" title="${{c.n}}">${{c.n}}</span><span class="ft">${{c.t}}</span><span class="fc" title="${{c.c}}">${{c.c}}</span></div>`;
  }}).join('');
  const tr=document.getElementById('tr');
  const ol=(adjOut[id]||[]).map(e=>`<div class="ri"><div><span class="ra">→</span><span class="rt">${{e.target}}</span></div>${{e.pairs.map(p=>`<div class="rd">${{p.desc}}</div><div class="rf">${{p.sf}} → ${{p.tf}}</div>`).join('')}}</div>`);
  const il=(adjIn[id]||[]).map(e=>`<div class="ri"><div><span class="ra">←</span><span class="rt">${{e.source}}</span></div>${{e.pairs.map(p=>`<div class="rd">${{p.desc}}</div><div class="rf">${{p.sf}} ← ${{p.tf}}</div>`).join('')}}</div>`);
  tr.innerHTML=ol.concat(il).join('')||`<div style="padding:10px;color:var(--dim);font-size:13px">无关联</div>`;
  document.getElementById('det').classList.remove('hide');
  showTab('f');
  if(hiCol)setTimeout(()=>{{const f=tf.querySelector('.mf');if(f)f.scrollIntoView({{block:'nearest'}});}},50);
  document.querySelectorAll('.st').forEach(el=>el.classList.remove('active'));
  const sbEl=document.getElementById('sb_'+id);
  if(sbEl){{sbEl.classList.add('active');sbEl.scrollIntoView({{block:'nearest',behavior:'smooth'}});}}
}}
function closeDet(){{
  document.getElementById('det').classList.add('hide');activeId=null;
  document.querySelectorAll('.st').forEach(el=>el.classList.remove('active'));
  chart.dispatchAction({{type:'downplay'}});
}}
function showTab(t){{
  document.getElementById('tf').className=t==='f'?'show':'';
  document.getElementById('tr').className=t==='r'?'show':'';
  document.getElementById('tab-tf').className='tab'+(t==='f'?' on':'');
  document.getElementById('tab-tr').className='tab'+(t==='r'?' on':'');
}}
// ── sidebar ──────────────────────────────────────────────────────────────────
const sbBody=document.getElementById('sb-body');
function buildSidebar(filter){{
  const q=(filter||'').toLowerCase();
  const grpOrder=[...new Set(NODES.map(n=>n.grp))];
  const grpColor={{}};NODES.forEach(n=>{{grpColor[n.grp]=n.itemStyle?.borderColor||'#64748b';}});
  sbBody.innerHTML='';
  grpOrder.forEach(grp=>{{
    const tbls=NODES.filter(n=>n.grp===grp&&(!q||n.id.toLowerCase().includes(q)||n.sub.toLowerCase().includes(q)));
    if(!tbls.length)return;
    const color=grpColor[grp];
    const ge=document.createElement('div');ge.className='sg';
    const he=document.createElement('div');he.className='sg-hd';
    he.innerHTML=`<div class="gdot" style="background:${{color}}"></div><span>${{grp}} (${{tbls.length}})</span><span class="ga">▾</span>`;
    const ie=document.createElement('div');ie.className='sg-items';
    he.addEventListener('click',()=>{{he.classList.toggle('col');ie.classList.toggle('hide');}});
    tbls.forEach(n=>{{
      const el=document.createElement('div');
      el.className='st'+(n.id===activeId?' active':'');el.id='sb_'+n.id;
      el.innerHTML=`<span class="st-n">${{n.id}}</span><span class="st-s">${{n.sub}}</span>`;
      el.addEventListener('click',()=>{{
        openDet(n.id);
        const idx=NODES.findIndex(x=>x.id===n.id);
        if(idx>=0)chart.dispatchAction({{type:'highlight',seriesIndex:0,dataIndex:[idx]}});
      }});
      ie.appendChild(el);
    }});
    ge.appendChild(he);ge.appendChild(ie);sbBody.appendChild(ge);
  }});
}}
buildSidebar();
document.getElementById('sb-q').addEventListener('input',e=>buildSidebar(e.target.value));
// ── search ───────────────────────────────────────────────────────────────────
const searchEl=document.getElementById('search'),scEl=document.getElementById('sc'),srEl=document.getElementById('sr');
function hiStr(str,q){{
  if(!q)return str;
  return str.replace(new RegExp('('+q.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&')+')','gi'),'<mark class="hi">$1</mark>');
}}
searchEl.addEventListener('input',()=>{{
  const q=searchEl.value.trim().toLowerCase();
  if(!q){{srEl.style.display='none';scEl.textContent='';chart.dispatchAction({{type:'downplay'}});return;}}
  const res=NODES.map(n=>{{
    const th=n.id.toLowerCase().includes(q)||n.sub.toLowerCase().includes(q);
    const ch=n.colData.filter(c=>c.n.toLowerCase().includes(q)||c.c.toLowerCase().includes(q));
    return(!th&&!ch.length)?null:{{n,th,ch}};
  }}).filter(Boolean);
  scEl.textContent=res.length?res.length+'个':'无';
  chart.dispatchAction({{type:'highlight',seriesIndex:0,dataIndex:res.map(r=>NODES.findIndex(x=>x.id===r.n.id)).filter(i=>i>=0)}});
  srEl.innerHTML=res.length
    ?res.slice(0,40).map(({{n,ch}})=>
        `<div class="sr-row" onclick="pickSearch('${{n.id}}','${{q}}')">
          <div class="sr-tn">${{hiStr(n.id,q)}}</div>
          <div class="sr-sub">${{hiStr(n.sub,q)}}</div>
          ${{ch.length?'<div class="sr-col">'+ch.slice(0,3).map(c=>hiStr(c.n,q)+(c.c?' — '+hiStr(c.c,q):'')).join('  ')+'</div>':''}}
        </div>`).join('')
    :`<div style="padding:10px 12px;color:var(--dim);font-size:13px">无匹配</div>`;
  srEl.style.display='block';
}});
function pickSearch(id,q){{
  srEl.style.display='none';searchEl.value='';scEl.textContent='';
  chart.dispatchAction({{type:'downplay'}});openDet(id,q);
  const idx=NODES.findIndex(x=>x.id===id);
  if(idx>=0)chart.dispatchAction({{type:'highlight',seriesIndex:0,dataIndex:[idx]}});
}}
document.addEventListener('click',e=>{{if(!e.target.closest('#sw')&&!e.target.closest('#sr'))srEl.style.display='none';}});
// ── legend ───────────────────────────────────────────────────────────────────
function buildLegend(){{
  const lg=document.getElementById('legend');lg.innerHTML='';
  const gc={{}};NODES.forEach(n=>{{gc[n.grp]=n.itemStyle?.borderColor||'#64748b';}});
  Object.entries(gc).forEach(([label,color])=>{{
    const cnt=NODES.filter(n=>n.grp===label).length;
    const li=document.createElement('div');
    li.className='li'+(hiddenGrps.has(label)?' off':'');
    li.innerHTML=`<div class="ld" style="background:${{color}}25;border:1.5px solid ${{color}}"></div><span>${{label}}(${{cnt}})</span>`;
    li.title='点击切换显示';
    li.addEventListener('click',()=>{{hiddenGrps.has(label)?hiddenGrps.delete(label):hiddenGrps.add(label);buildLegend();chart.setOption(buildOption());}});
    lg.appendChild(li);
  }});
}}
buildLegend();
// ── controls ─────────────────────────────────────────────────────────────────
function toggleSb(){{
  const el=document.getElementById('sb'),btn=document.getElementById('btn-sb');
  el.classList.toggle('hide');const h=el.classList.contains('hide');
  btn.textContent=h?'显示列表':'隐藏列表';btn.classList.toggle('on',!h);
  setTimeout(()=>chart.resize(),180);
}}
function toggleLabels(){{
  showLabels=!showLabels;const btn=document.getElementById('btn-labels');
  btn.textContent=showLabels?'隐藏标签':'显示标签';btn.classList.toggle('on',showLabels);
  chart.setOption(buildOption());
}}
function toggleNM(){{
  nameMode=nameMode==='en'?'cn':'en';const btn=document.getElementById('btn-nm');
  btn.textContent=nameMode==='en'?'显示中文名':'显示表名';btn.classList.toggle('on',nameMode==='cn');
  chart.setOption(buildOption());
}}
function toggleTheme(){{
  darkMode=!darkMode;
  document.documentElement.setAttribute('data-theme',darkMode?'dark':'light');
  document.getElementById('btn-theme').textContent=darkMode?'☀ 亮色模式':'🌙 暗色模式';
  chart.dispose();chart=initChart();chart.setOption(buildOption());
  setTimeout(()=>chart.resize(),50);
}}
function resetView(){{hiddenGrps.clear();buildLegend();chart.setOption(buildOption(),true);}}
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────────

class ERGenerator:
    def __init__(self,
                 dsn: Optional[str] = None,
                 schema_file: Optional[str] = None,
                 tables: Optional[list[str]] = None,
                 exclude: Optional[list[str]] = None,
                 output: str = 'er-diagram.html',
                 title: str = '数据库可交互关系图',
                 font_size: int = 16,
                 theme: str = 'dark',
                 no_infer_rels: bool = False,
                 fold_n: int = 10):
        self.dsn = dsn
        self.schema_file = schema_file
        self.tables = tables or []
        self.exclude = exclude or []
        self.output = output
        self.title = title
        self.font_size = font_size
        self.theme = theme
        self.no_infer_rels = no_infer_rels
        self.fold_n = fold_n

    def load_schema(self) -> dict:
        if self.schema_file:
            with open(self.schema_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        if not self.dsn:
            raise ValueError("Either --dsn or --schema-file is required")

        dsn = self.dsn
        if dsn.startswith('mysql://') or dsn.startswith('mariadb://'):
            return fetch_mysql(dsn, self.tables, self.exclude)
        elif dsn.startswith('postgres://') or dsn.startswith('postgresql://'):
            return fetch_postgres(dsn, self.tables, self.exclude)
        elif dsn.startswith('sqlserver://') or dsn.startswith('mssql://'):
            return fetch_sqlserver(dsn, self.tables, self.exclude)
        elif dsn.startswith('sqlite://'):
            return fetch_sqlite(dsn, self.tables, self.exclude)
        else:
            raise ValueError(f"Unsupported DSN scheme: {dsn}")

    def run(self):
        print(f"Loading schema…")
        schema = self.load_schema()
        print(f"  {len(schema)} tables loaded")

        print("Inferring relationships…")
        rels = infer_relations(schema, no_infer=self.no_infer_rels)
        print(f"  {len(rels)} relationships found")

        print("Computing layout…")
        groups = assign_groups(schema)
        groups_layout, canvas_w, canvas_h = compute_layout(schema, groups, self.fold_n)

        print("Building JS data…")
        data_js = build_js_data(schema, groups_layout, rels, self.fold_n)

        print(f"Generating HTML → {self.output}")
        html = build_html(
            title=self.title,
            data_js=data_js,
            theme=self.theme,
            font_size=self.font_size,
            fold_n=self.fold_n,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
        )
        with open(self.output, 'w', encoding='utf-8') as f:
            f.write(html)
        size_kb = len(html.encode()) // 1024
        print(f"Done. Output: {self.output} ({size_kb} KB)")


def main():
    parser = argparse.ArgumentParser(
        description='Generate an interactive ER diagram HTML from a database.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate.py --dsn "mysql://root:pass@localhost:3306/mydb"
  python generate.py --dsn "postgres://admin:pass@host:5432/shop" --tables "users,orders,products"
  python generate.py --dsn "sqlite:///app.db" --output myapp.html --theme light
  python generate.py --schema-file schema.json --output er.html --title "My System"
""")
    parser.add_argument('--dsn',            help='Database connection string')
    parser.add_argument('--schema-file',    help='Path to JSON schema file (offline mode)')
    parser.add_argument('--output',         default='er-diagram.html', help='Output HTML file path')
    parser.add_argument('--title',          default='数据库可交互关系图', help='Page title')
    parser.add_argument('--tables',         help='Comma-separated table whitelist')
    parser.add_argument('--exclude',        help='Comma-separated table blacklist')
    parser.add_argument('--font-size',      type=int, default=16, help='Base font size in px (default: 16)')
    parser.add_argument('--theme',          default='dark', choices=['dark', 'light'], help='Initial theme')
    parser.add_argument('--no-infer-rels',  action='store_true', help='Disable automatic relationship inference')
    parser.add_argument('--max-cols-preview', type=int, default=10, dest='fold_n',
                        help='Max columns shown before folding (default: 10)')
    args = parser.parse_args()

    ERGenerator(
        dsn=args.dsn,
        schema_file=args.schema_file,
        tables=[t.strip() for t in args.tables.split(',')] if args.tables else [],
        exclude=[t.strip() for t in args.exclude.split(',')] if args.exclude else [],
        output=args.output,
        title=args.title,
        font_size=args.font_size,
        theme=args.theme,
        no_infer_rels=args.no_infer_rels,
        fold_n=args.fold_n,
    ).run()


if __name__ == '__main__':
    main()
