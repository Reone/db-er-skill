# db-er-skill

[English](README.md)

从任意数据库（MySQL、PostgreSQL、SQL Server 或 SQLite）一键生成可交互的自包含 ER 图 HTML 文件，无需任何前端构建步骤。

## 功能特性

- 基于 ECharts 5 的力导向图，自动推断表间关联关系
- 左侧表列表：按业务分组展示，支持实时过滤
- 右侧详情面板：显示所选表的字段明细 + 关联关系
- 顶部搜索：匹配表名、字段名、字段注释
- 暗色 / 亮色主题切换
- 节点标签切换：英文表名 ↔ 中文注释
- 生成单个 HTML 文件，离线可用，开箱即看

## 快速开始

```bash
pip install pymysql   # 或 psycopg2-binary / pymssql
python generate.py --dsn "mysql://root:pass@localhost:3306/mydb"
```

用浏览器打开生成的 `er-diagram.html` 即可。

## 用法

```
python generate.py [选项]

选项：
  --dsn             数据库连接串（未指定 --schema-file 时必填）
  --schema-file     JSON schema 文件路径（离线 / CI 模式）
  --output          输出 HTML 路径   [默认：er-diagram.html]
  --title           页面标题         [默认：数据库可交互关系图]
  --tables          表名白名单，逗号分隔
  --exclude         表名黑名单，逗号分隔
  --font-size       基础字号（px）   [默认：16，经实际使用验证，阅读舒适度优于 14px]
  --theme           dark | light     [默认：dark]
  --no-infer-rels   禁用自动关联推断
  --max-cols-preview 折叠前显示的最大列数 [默认：10]
```

### 连接串格式

| 数据库 | 连接串示例 |
|--------|------------|
| MySQL | `mysql://root:pass@host:3306/dbname` |
| PostgreSQL | `postgres://user:pass@host:5432/dbname` |
| SQL Server | `sqlserver://sa:pass@host:1433/dbname` |
| SQLite | `sqlite:///path/to/file.db` |

### 作为 Python 模块调用

```python
from generate import ERGenerator

ERGenerator(
    dsn="mysql://root:pass@localhost:3306/shop",
    tables=["users", "orders", "products", "order_items"],
    output="shop-er.html",
    title="电商系统 ER 图",
    theme="light",
).run()
```

### Claude Code skill 使用方式

安装为 skill 后，在 Claude Code 中输入 `/db-er` 并按照提示操作即可。

## 离线 / CI 模式

先将 schema 导出为 JSON 文件，之后生成 HTML 无需再连接数据库：

```bash
# 从线上数据库导出 schema
python generate.py --dsn "mysql://..." --output schema.json --schema-only

# 从 JSON 离线生成 HTML（适合 CI 环境）
python generate.py --schema-file schema.json --output er.html
```

schema JSON 格式说明：

```json
{
  "users": {
    "comment": "用户表",
    "cols": [
      {"key": "PRI", "col": "id",      "type": "int",     "cmt": "主键"},
      {"key": "UNI", "col": "email",   "type": "varchar", "cmt": "邮箱"},
      {"key": "MUL", "col": "role_id", "type": "int",     "cmt": "→ roles.id"}
    ]
  }
}
```

## 关联关系推断逻辑

1. **显式注释标注** — 字段注释中包含 `→ table.col` 形式的文本
2. **`_id` 后缀匹配** — `role_id` → 查找表名 `role` 或 `roles`，关联到其主键
3. **`fk_` 前缀匹配** — `fk_user` → 查找表名 `user` 或 `users`
4. **共享 PK/UK 字段** — 两张表拥有相同名称的非平凡唯一字段

使用 `--no-infer-rels` 可关闭自动推断，仅保留显式注释标注的关联。

## 依赖安装

```
pymysql>=1.1.0         # MySQL / MariaDB
psycopg2-binary>=2.9.0 # PostgreSQL
pymssql>=2.3.0         # SQL Server
```

SQLite 使用 Python 内置的 `sqlite3` 模块，无需额外安装。

## 示例

- [`examples/student-system-er.html`](examples/student-system-er.html) — 学生管理系统（19张表）
- [`examples/student-system-er.png`](examples/student-system-er.png) — 学生管理系统截图
- [`examples/ecommerce-er.html`](examples/ecommerce-er.html) — 电商订单系统（15张表，亮色主题）
- [`examples/ecommerce-er.png`](examples/ecommerce-er.png) — 电商订单系统截图

## 许可证

MIT
