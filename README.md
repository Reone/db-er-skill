# db-er-skill

Generate a fully self-contained, interactive ER diagram HTML file from any database — MySQL, PostgreSQL, SQL Server, or SQLite — with zero front-end build steps.

## Features

- Force-directed graph (ECharts 5) with automatic relationship inference
- Left sidebar: table list grouped by business domain, filterable
- Right panel: field details + relationship list per selected table
- Top search: matches table names, field names, and field comments
- Dark / light theme toggle
- Node label toggle: English table name ↔ Chinese comment
- Self-contained single HTML file, works offline after generation

## Quick start

```bash
pip install pymysql   # or psycopg2-binary / pymssql
python generate.py --dsn "mysql://root:pass@localhost:3306/mydb"
```

Open the generated `er-diagram.html` in any browser.

## Usage

```
python generate.py [options]

Options:
  --dsn             Database connection string (required unless --schema-file given)
  --schema-file     Path to JSON schema (offline / CI mode)
  --output          Output HTML path   [default: er-diagram.html]
  --title           Page title         [default: 数据库可交互关系图]
  --tables          Comma-separated table whitelist
  --exclude         Comma-separated table blacklist
  --font-size       Base font size px  [default: 16, recommended — verified more readable than 14px]
  --theme           dark | light       [default: dark]
  --no-infer-rels   Disable automatic relationship inference
  --max-cols-preview Max columns before folding [default: 10]
```

### DSN formats

| Database | DSN example |
|----------|-------------|
| MySQL | `mysql://root:pass@host:3306/dbname` |
| PostgreSQL | `postgres://user:pass@host:5432/dbname` |
| SQL Server | `sqlserver://sa:pass@host:1433/dbname` |
| SQLite | `sqlite:///path/to/file.db` |

### As a Python module

```python
from generate import ERGenerator

ERGenerator(
    dsn="mysql://root:pass@localhost:3306/shop",
    tables=["users", "orders", "products", "order_items"],
    output="shop-er.html",
    title="Shop ER Diagram",
    theme="light",
).run()
```

### Claude Code skill

Once installed as a skill, type `/db-er` in Claude Code and follow the prompts.

## Offline / CI mode

Export schema to JSON first (no database access needed for HTML generation):

```bash
# Export schema from live database
python generate.py --dsn "mysql://..." --output schema.json --schema-only

# Generate HTML from JSON (e.g. in CI without DB access)
python generate.py --schema-file schema.json --output er.html
```

Schema JSON format:

```json
{
  "users": {
    "comment": "User accounts",
    "cols": [
      {"key": "PRI", "col": "id",       "type": "int",     "cmt": "Primary key"},
      {"key": "UNI", "col": "email",    "type": "varchar", "cmt": "Email address"},
      {"key": "MUL", "col": "role_id",  "type": "int",     "cmt": "→ roles.id"}
    ]
  }
}
```

## Relationship inference

1. **Explicit annotation** — field comment contains `→ table.col`
2. **`_id` suffix** — `role_id` → looks for table `role` or `roles`, links to its PK
3. **`fk_` prefix** — `fk_user` → looks for table `user` or `users`
4. **Shared PK/UK fields** — two tables with the same non-trivial unique field name

Use `--no-infer-rels` to show only explicitly annotated relationships.

## Requirements

```
pymysql>=1.1.0         # MySQL / MariaDB
psycopg2-binary>=2.9.0 # PostgreSQL
pymssql>=2.3.0         # SQL Server
```

SQLite uses Python's built-in `sqlite3` — no extra install needed.

## Examples

- [`examples/student-system-er.html`](examples/student-system-er.html) — Student management system (20 tables)
- [`examples/ecommerce-er.html`](examples/ecommerce-er.html) — E-commerce order system (15 tables)

## License

MIT
