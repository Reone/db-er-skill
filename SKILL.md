---
description: Generate an interactive ER diagram HTML file from a database. Supports MySQL, PostgreSQL, SQL Server, and SQLite. Outputs a self-contained HTML with force-directed graph visualization (ECharts), relationship inference, field search, dark/light theme, and table list sidebar.
---

# DB ER Skill — 数据库可交互关系图生成器

## 功能概述

从指定数据库（或指定若干表）自动生成一份自包含的可交互 ER 图 HTML 文件，无需安装任何前端依赖。图表使用 ECharts 力导向图，支持：

- 按业务分组展示所有表
- 自动推断表间关联关系（基于字段名语义）
- 右侧详情面板（字段列表 + 关联关系两个标签）
- 左侧表列表导航（可过滤，点击定位节点）
- 顶部搜索（支持表名、字段名、字段注释）
- 暗色 / 亮色主题切换
- 节点标签支持英文表名 / 中文注释切换

## 支持的数据库

| 类型 | 驱动 | 连接串格式 |
|------|------|------------|
| MySQL / MariaDB | `pymysql` | `mysql://user:pass@host:3306/dbname` |
| PostgreSQL | `psycopg2` | `postgres://user:pass@host:5432/dbname` |
| SQL Server | `pymssql` | `sqlserver://user:pass@host:1433/dbname` |
| SQLite | 内置 | `sqlite:///path/to/file.db` |

## 使用方式

### 方式一：直接调用此 skill（Claude Code 环境）

在 Claude Code 终端输入：

```
/db-er
```

然后按照提示提供数据库连接信息。

### 方式二：命令行直接运行

```bash
python generate.py \
  --dsn "mysql://root:password@localhost:3306/mydb" \
  --output "er-diagram.html" \
  --title "我的系统 ER 图"
```

只分析特定表：

```bash
python generate.py \
  --dsn "mysql://root:password@localhost:3306/mydb" \
  --tables "users,orders,products,order_items" \
  --output "er-diagram.html"
```

排除某些表：

```bash
python generate.py \
  --dsn "postgres://admin:secret@db.example.com:5432/shop" \
  --exclude "flyway_history,schema_migrations,audit_log" \
  --output "shop-er.html"
```

从已有 JSON schema 文件生成（离线模式）：

```bash
python generate.py \
  --schema-file schema.json \
  --output er-diagram.html
```

### 方式三：作为 Python 模块调用

```python
from generate import ERGenerator

gen = ERGenerator(
    dsn="mysql://root:password@localhost:3306/myapp",
    tables=["users", "roles", "permissions"],  # 可选，为空则全库
    output="myapp-er.html",
    title="MyApp 权限模块 ER 图",
    font_size=16,  # 基础字号，默认16
)
gen.run()
```

## 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--dsn` | str | 必填 | 数据库连接串 |
| `--output` | str | `er-diagram.html` | 输出 HTML 文件路径 |
| `--title` | str | `数据库可交互关系图` | 页面标题 |
| `--tables` | str | 全库 | 逗号分隔的表名白名单 |
| `--exclude` | str | 空 | 逗号分隔的表名黑名单 |
| `--schema-file` | str | 空 | 直接从 JSON schema 文件生成，跳过数据库连接 |
| `--font-size` | int | `16` | 基础字号（px），sm=base-2，xs=base-4。16px 为推荐值，经实际使用验证阅读舒适度优于 14px |
| `--theme` | str | `dark` | 初始主题 `dark` 或 `light` |
| `--no-infer-rels` | flag | 关 | 禁用自动关联推断，仅显示显式外键 |
| `--max-cols-preview` | int | `10` | 节点折叠前显示的最大列数 |

## schema-file 格式

如果无法直接连接数据库，可先导出 schema JSON 再离线生成：

```json
{
  "users": {
    "comment": "用户表",
    "cols": [
      {"key": "PRI", "col": "id",       "type": "int",     "cmt": "主键"},
      {"key": "UNI", "col": "email",    "type": "varchar", "cmt": "邮箱"},
      {"key": "",    "col": "username", "type": "varchar", "cmt": "用户名"},
      {"key": "MUL", "col": "role_id",  "type": "int",     "cmt": "角色ID"}
    ]
  },
  "roles": {
    "comment": "角色表",
    "cols": [
      {"key": "PRI", "col": "id",   "type": "int",     "cmt": "主键"},
      {"key": "",    "col": "name", "type": "varchar", "cmt": "角色名称"}
    ]
  }
}
```

## 关联关系推断逻辑

脚本按以下优先级推断关联：

1. **显式外键**：若数据库中存在 `FOREIGN KEY` 约束，直接使用
2. **字段名精确匹配**：`table_b.user_id` 中 `user_id` 去掉 `_id` 后缀得 `user`，匹配表名 `users` 或 `user`
3. **字段注释关键词**：注释中包含 `→ table.col` 形式的文本
4. **同名字段传递**：两表都有同名 PK/UK 字段（如都有 `dept_code`），视为可能关联

使用 `--no-infer-rels` 可关闭 2/3/4，仅保留显式外键。

## 示例

- [示例1：学生管理系统](examples/student-system-er.html) — 20张表，MySQL
- [示例2：电商订单系统](examples/ecommerce-er.html) — 15张表，PostgreSQL 风格

## 安装依赖

```bash
pip install pymysql psycopg2-binary pymssql
```

SQLite 使用 Python 内置驱动，无需额外安装。
