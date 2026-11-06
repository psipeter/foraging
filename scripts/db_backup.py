"""A local copy of the online database, table by table, before a migration changes its schema.

    ./venv/bin/python scripts/db_backup.py [--out ForagingData] [--label legacy]

Reads every table of the `public` schema through the Supabase CLI (`supabase db query --remote --read-only`, as `human_data.py` does; the CLI must be
logged in to the linked project) and writes, under `<out>/_db_backup_<label>_<UTC time>/` (ForagingData is gitignored and holds participant names). Pages are cut in primary-key order; run it while
no one is playing (a row inserted meanwhile can shift a page):

    <table>.jsonl     one JSON object per row (`to_jsonb`: a bytea column is its hex text, a timestamp is text, nothing is lost)
    schema.json       the columns of every table (information_schema) and the migrations the project has applied
    counts.json       rows per table, as read, for checking the copy

It does not need the schema of any migration: it takes the tables as it finds them, so it works before and after one. To restore a table, insert its rows with
`jsonb_populate_recordset` (the migrations in supabase/migrations/ recreate the schema; the first three are the legacy one).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from human_data import query

PAGE = 1000
ROOT = Path(__file__).resolve().parent.parent


def backup(out, label="legacy", log=print):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = Path(out) / f"_db_backup_{label}_{stamp}"
    folder.mkdir(parents=True)
    tables = [r["table_name"] for r in query("select table_name from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE' order by table_name")]
    columns = query("select table_name, column_name, data_type, is_nullable, ordinal_position from information_schema.columns where table_schema = 'public' order by table_name, ordinal_position")
    try:
        migrations = query("select version, name from supabase_migrations.schema_migrations order by version")
    except RuntimeError as e:
        migrations = [{"error": str(e)[:200]}]
    (folder / "schema.json").write_text(json.dumps({"tables": tables, "columns": columns, "migrations": migrations}, indent=1, default=str))
    counts = {}
    keys = {}                                              # a table's primary key columns: pages are cut in a stable order
    for r in query("select tc.table_name, kcu.column_name from information_schema.table_constraints tc join information_schema.key_column_usage kcu "
                   "on kcu.constraint_name = tc.constraint_name and kcu.table_schema = tc.table_schema "
                   "where tc.table_schema = 'public' and tc.constraint_type = 'PRIMARY KEY' order by tc.table_name, kcu.ordinal_position"):
        keys.setdefault(r["table_name"], []).append(f'"{r["column_name"]}"')
    for table in tables:
        n = 0
        order = ", ".join(keys.get(table, ["ctid"]))
        with open(folder / f"{table}.jsonl", "w") as f:
            while True:
                rows = query(f'select to_jsonb(t) as r from public."{table}" t order by {order} limit {PAGE} offset {n}')
                for row in rows:
                    f.write(json.dumps(row["r"], default=str) + "\n")
                n += len(rows)
                if len(rows) < PAGE:
                    break
        counts[table] = n
        log(f"  {table}: {n} rows")
    (folder / "counts.json").write_text(json.dumps(counts, indent=1))
    return folder, counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default=str(ROOT / "ForagingData"))
    parser.add_argument("--label", default="legacy")
    args = parser.parse_args(argv)
    folder, counts = backup(args.out, args.label)
    print(f"{sum(counts.values())} rows in {len(counts)} tables written to {folder}")


if __name__ == "__main__":
    sys.exit(main())
