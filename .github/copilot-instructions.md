# GitHub Copilot Instructions — db-er-skill

This project contains `generate.py`, a command-line tool that generates a self-contained
interactive ER diagram HTML file from a database schema.

## When to use this tool

Use `generate.py` when the user asks to:
- Generate an ER diagram or database relationship diagram
- Visualize a database schema
- Document table relationships
- Explore connections between tables in a database

## How to invoke

```bash
# Connect to a live database
python generate.py --dsn "mysql://user:pass@host:3306/dbname" --output er.html

# Use a pre-exported JSON schema (offline / CI)
python generate.py --schema-file schema.json --output er.html

# Analyze specific tables only
python generate.py --dsn "mysql://..." --tables "users,orders,products" --output er.html

# Exclude noise tables
python generate.py --dsn "mysql://..." --exclude "flyway_history,audit_log" --output er.html
```

## Connection string formats

| Database     | DSN format                                  |
|--------------|---------------------------------------------|
| MySQL        | `mysql://user:pass@host:3306/dbname`        |
| PostgreSQL   | `postgres://user:pass@host:5432/dbname`     |
| SQL Server   | `sqlserver://sa:pass@host:1433/dbname`      |
| SQLite       | `sqlite:///path/to/file.db`                 |

## Common options

| Option                | Default              | Description                                    |
|-----------------------|----------------------|------------------------------------------------|
| `--output`            | `er-diagram.html`    | Output HTML file path                          |
| `--title`             | `数据库可交互关系图`  | Page title                                     |
| `--tables`            | all                  | Comma-separated table whitelist                |
| `--exclude`           | none                 | Comma-separated table blacklist                |
| `--font-size`         | `16`                 | Base font size in px                           |
| `--theme`             | `dark`               | `dark` or `light`                              |
| `--no-infer-rels`     | off                  | Disable automatic relationship inference       |
| `--max-cols-preview`  | `10`                 | Max columns shown before folding               |

## Python API

```python
from generate import ERGenerator

ERGenerator(
    dsn="mysql://root:pass@localhost:3306/mydb",
    output="er.html",
    title="My System ER Diagram",
    theme="light",
).run()
```

## Schema JSON format (offline mode)

```json
{
  "table_name": {
    "comment": "Table description",
    "cols": [
      {"key": "PRI", "col": "id",      "type": "int",     "cmt": "Primary key"},
      {"key": "UNI", "col": "email",   "type": "varchar", "cmt": "Email address"},
      {"key": "MUL", "col": "role_id", "type": "int",     "cmt": "→ roles.id"}
    ]
  }
}
```

Write `→ target_table.column` in a field's `cmt` to explicitly declare a relationship.
