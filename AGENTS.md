# db-er-skill — Agent Instructions

This project provides `generate.py`, a command-line tool that generates a self-contained
interactive ER diagram HTML file from a database schema.

## What this tool does

Run `generate.py` to connect to a database, read its schema, infer relationships between
tables, and produce a single HTML file containing a force-directed graph visualization
(powered by ECharts). The output works offline in any browser.

## How to invoke it

```bash
# From a live database
python generate.py --dsn "mysql://user:pass@host:3306/dbname" --output er.html

# From a pre-exported JSON schema file (no DB access needed)
python generate.py --schema-file schema.json --output er.html

# Specific tables only
python generate.py --dsn "mysql://..." --tables "users,orders,products" --output er.html

# Exclude migration/audit tables
python generate.py --dsn "mysql://..." --exclude "flyway_history,audit_log" --output er.html
```

## Full option reference

| Option | Default | Description |
|--------|---------|-------------|
| `--dsn` | required | Database connection string (see formats below) |
| `--schema-file` | — | Path to a JSON schema file for offline generation |
| `--output` | `er-diagram.html` | Output HTML file path |
| `--title` | `数据库可交互关系图` | Page title shown in the browser tab |
| `--tables` | all tables | Comma-separated whitelist of table names |
| `--exclude` | none | Comma-separated blacklist of table names |
| `--font-size` | `16` | Base font size in px (16 recommended for readability) |
| `--theme` | `dark` | Initial color theme: `dark` or `light` |
| `--no-infer-rels` | off | Disable automatic relationship inference |
| `--max-cols-preview` | `10` | Max columns shown per table before folding |

## DSN connection string formats

```
mysql://user:password@host:3306/database
postgres://user:password@host:5432/database
sqlserver://user:password@host:1433/database
sqlite:///path/to/file.db
```

## Python module usage

```python
from generate import ERGenerator

ERGenerator(
    dsn="mysql://root:pass@localhost:3306/myapp",
    tables=["users", "roles", "permissions"],
    output="myapp-er.html",
    title="MyApp ER Diagram",
    theme="light",
    font_size=16,
).run()
```

## Schema JSON format (for offline mode)

```json
{
  "users": {
    "comment": "User accounts",
    "cols": [
      {"key": "PRI", "col": "id",      "type": "int",     "cmt": "Primary key"},
      {"key": "UNI", "col": "email",   "type": "varchar", "cmt": "Email address"},
      {"key": "MUL", "col": "role_id", "type": "int",     "cmt": "→ roles.id"}
    ]
  }
}
```

Field `key` values: `PRI` = primary key, `UNI` = unique, `MUL` = indexed / foreign key.

To annotate an explicit relationship, write `→ target_table.column` in the `cmt` field.

## Relationship inference rules

The generator automatically infers relationships using these rules (in priority order):

1. **Explicit comment annotation** — `cmt` contains `→ table.col`
2. **`_id` suffix** — a field named `role_id` looks for a table named `role` or `roles`
3. **`fk_` prefix** — a field named `fk_user` looks for a table named `user` or `users`
4. **Shared unique fields** — two tables share the same non-trivial PK/UK field name

Use `--no-infer-rels` to disable rules 2–4 and keep only explicit annotations.

## Install dependencies

```bash
pip install pymysql              # MySQL / MariaDB
pip install psycopg2-binary      # PostgreSQL
pip install pymssql              # SQL Server
# SQLite: no install needed (Python built-in)
```

## When to use this tool

Ask the agent to run `generate.py` when:
- You need a visual overview of a database schema
- You are onboarding to a new codebase and want to understand table relationships
- You want to document a database for a README or design doc
- You need to find all tables connected to a specific table

## Output file features

The generated HTML contains:
- Force-directed graph with all tables as nodes and inferred relationships as edges
- Left sidebar: table list grouped by naming prefix, filterable
- Right panel: field list (name, type, comment, PK/UK/index badge) + relationship list
- Top search bar: searches table names, field names, and field comments simultaneously
- Dark/light theme toggle button
- Node label toggle: English table name ↔ Chinese comment
- Click on blank area to deselect; click a node to see its details
