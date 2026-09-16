#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Location: ./scripts/migrate_sqlite_to_postgres.py
Copyright contributors to the MCP-CONTEXT-FORGE project
SPDX-License-Identifier: Apache-2.0

Copy ContextForge data from a SQLite database into PostgreSQL.

The script reflects both schemas, matches tables by name, and copies rows in
foreign-key-safe order. It never creates or alters schema: create the target
schema first with ``alembic upgrade head``.

Modes:
    replace        Truncate the target tables, then copy every source row.
                   Requires --yes because it destroys target data.
    skip-existing  Insert only rows whose primary key is absent from the
                   target. Existing target rows stay untouched.

Both databases must be at the same Alembic revision. The script reads the
``alembic_version`` table of each database and stops when the revisions differ.

Verification runs after every copy. Mode ``replace`` requires the two databases
to match exactly. Mode ``skip-existing`` requires the target to contain every
source row, and allows extra target rows.

Usage:
    # Report what would be copied without writing anything
    python scripts/migrate_sqlite_to_postgres.py --dry-run

    # Copy everything, replacing the target content
    python scripts/migrate_sqlite_to_postgres.py --mode replace --yes

    # Add only rows that PostgreSQL does not have yet
    python scripts/migrate_sqlite_to_postgres.py --mode skip-existing

    # Compare the two databases without writing
    python scripts/migrate_sqlite_to_postgres.py --verify-only --mode skip-existing

    # Copy a subset of tables
    python scripts/migrate_sqlite_to_postgres.py --mode replace --yes --tables tools,gateways

Exit codes:
    0  Copy and verification succeeded
    1  Invalid input, connection failure, or copy failure
    2  Verification mismatch between source and target
"""

# Standard
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Third-Party
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("migrate_sqlite_to_postgres")

# SQLite bookkeeping and Alembic's own table are never copied. The target keeps
# its own revision marker, which the script validates before any write.
SKIP_TABLES = frozenset({"sqlite_sequence", "alembic_version"})

# Rows per INSERT statement.
DEFAULT_BATCH_SIZE = 500


def _read_env_database_url(env_path: Path) -> Optional[str]:
    """Read DATABASE_URL from a dotenv file.

    Args:
        env_path: Path to the dotenv file.

    Returns:
        Optional[str]: The first active DATABASE_URL value, or None when the
        file is absent or holds no active assignment.
    """
    if not env_path.is_file():
        return None
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith("DATABASE_URL="):
            continue
        value = line.split("=", 1)[1].strip().strip('"').strip("'")
        if value:
            return value
    return None


def _resolve_target_url(explicit: Optional[str]) -> str:
    """Resolve the PostgreSQL URL from the argument, the environment, or .env.

    Args:
        explicit: Value of --target, when the caller passed one.

    Returns:
        str: The resolved database URL.

    Raises:
        SystemExit: If no URL is available or the URL is not PostgreSQL.
    """
    candidate = explicit or os.environ.get("DATABASE_URL") or _read_env_database_url(Path(".env"))
    if not candidate:
        logger.error("No target database URL. Pass --target or set DATABASE_URL.")
        raise SystemExit(1)
    if not candidate.startswith("postgresql"):
        logger.error("The target must be a PostgreSQL URL such as postgresql+psycopg://user:pass@host:5432/mcp, got: %s", candidate)
        raise SystemExit(1)
    return candidate


def _reflect(engine: Engine) -> MetaData:
    """Reflect every table of one database.

    Args:
        engine: Engine bound to the database to reflect.

    Returns:
        MetaData: Reflected metadata.
    """
    metadata = MetaData()
    metadata.reflect(bind=engine)
    return metadata


def _alembic_revision(connection: Connection) -> Optional[str]:
    """Read the Alembic revision recorded in a database.

    Args:
        connection: Open connection to inspect.

    Returns:
        Optional[str]: The revision string, or None when the table is missing.
    """
    if not inspect(connection).has_table("alembic_version"):
        return None
    value = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return str(value) if value is not None else None


def _normalize(value: Any) -> Any:
    """Convert one column value into a form both backends compare equally.

    SQLite and PostgreSQL return different Python objects for the same logical
    value: naive versus timezone-aware datetimes, str versus dict for JSON,
    bytes versus memoryview for binary. Normalizing keeps verification honest
    without hiding real differences.

    Args:
        value: Raw value read from either database.

    Returns:
        Any: A JSON-comparable representation of the value.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _primary_key_columns(table: Table) -> List[str]:
    """Return the primary-key column names of a table.

    Args:
        table: Table to inspect.

    Returns:
        List[str]: Primary-key column names in declared order.
    """
    return [column.name for column in table.primary_key.columns]


def _is_integer_column(table: Table, column_name: str) -> bool:
    """Report whether a column holds integers.

    Args:
        table: Table that owns the column.
        column_name: Name of the column to test.

    Returns:
        bool: True when the column's Python type is int.
    """
    try:
        return table.c[column_name].type.python_type is int
    except NotImplementedError:
        return False


def _fetch_rows(connection: Connection, table: Table) -> List[Dict[str, Any]]:
    """Read every row of a table in primary-key order.

    Args:
        connection: Open connection to read from.
        table: Table to read.

    Returns:
        List[Dict[str, Any]]: One mapping per row.
    """
    statement = select(table)
    key_columns = _primary_key_columns(table)
    if key_columns:
        statement = statement.order_by(*[table.c[name] for name in key_columns])
    return [dict(row) for row in connection.execute(statement).mappings()]


def _row_fingerprint(row: Dict[str, Any]) -> str:
    """Build a canonical, comparable string for one row.

    Args:
        row: Row mapping to convert.

    Returns:
        str: Sorted JSON object of every normalized column value.
    """
    return json.dumps({column: _normalize(value) for column, value in sorted(row.items())}, sort_keys=True, default=str)


def _chunks(items: Sequence[Dict[str, Any]], size: int) -> Iterable[Sequence[Dict[str, Any]]]:
    """Split a row list into insert batches.

    Args:
        items: Rows to split.
        size: Maximum rows per batch.

    Yields:
        Sequence[Dict[str, Any]]: One batch of rows.
    """
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _disable_foreign_key_triggers(connection: Connection) -> bool:
    """Disable PostgreSQL foreign-key triggers for the current transaction.

    The dependency order already covers the normal case. Disabling the triggers
    also covers dependency cycles and rows whose parent row is absent from the
    source database.

    Args:
        connection: Open PostgreSQL connection.

    Returns:
        bool: True when triggers were disabled for this session.
    """
    try:
        # A savepoint keeps the outer transaction usable when the server
        # refuses the SET (it needs superuser or SET privilege on the parameter).
        with connection.begin_nested():
            connection.execute(text("SET session_replication_role = replica"))
        logger.info("Foreign-key triggers disabled for this session (session_replication_role=replica)")
        return True
    except SQLAlchemyError as exc:
        logger.warning("Cannot disable foreign-key triggers (%s); relying on dependency order", exc)
        return False


def _truncate_target(connection: Connection, tables: Sequence[Table]) -> None:
    """Remove every row from the selected target tables.

    Args:
        connection: Open PostgreSQL connection.
        tables: Tables to truncate.
    """
    names = ", ".join(f'"{table.name}"' for table in tables)
    # RESTART IDENTITY resets the sequences so the later setval pass starts clean.
    connection.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
    logger.info("Truncated %d target table(s)", len(tables))


def _reset_sequences(connection: Connection, tables: Sequence[Table]) -> List[str]:
    """Align PostgreSQL sequences with the copied rows.

    Without this step the next insert reuses an identifier that already exists.

    Args:
        connection: Open PostgreSQL connection.
        tables: Tables that were copied.

    Returns:
        List[str]: Names of the columns whose sequence was advanced.
    """
    reset: List[str] = []
    for table in tables:
        key_columns = _primary_key_columns(table)
        if len(key_columns) != 1:
            continue
        column = key_columns[0]
        if not _is_integer_column(table, column):
            continue
        # pg_get_serial_sequence returns NULL for a column without a sequence,
        # such as the varchar(36) identifiers most tables use.
        sequence = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": f'public."{table.name}"', "column_name": column},
        ).scalar()
        if not sequence:
            continue
        connection.execute(
            text(f'SELECT setval(:sequence, COALESCE((SELECT MAX("{column}") FROM "{table.name}"), 1), (SELECT COUNT(*) > 0 FROM "{table.name}"))'),
            {"sequence": sequence},
        )
        reset.append(f"{table.name}.{column}")
    return reset


def copy_tables(
    source: Engine,
    target: Engine,
    table_names: Sequence[str],
    mode: str,
    batch_size: int,
    dry_run: bool,
) -> Dict[str, int]:
    """Copy the selected tables from the source into the target.

    Args:
        source: Engine bound to the SQLite database.
        target: Engine bound to the PostgreSQL database.
        table_names: Tables to copy, in any order.
        mode: Either ``replace`` or ``skip-existing``.
        batch_size: Rows per INSERT statement.
        dry_run: When True, report counts without writing.

    Returns:
        Dict[str, int]: Rows copied per table.
    """
    source_metadata = _reflect(source)
    target_metadata = _reflect(target)

    # sorted_tables returns foreign-key-safe insert order.
    insert_order = [table.name for table in target_metadata.sorted_tables if table.name in table_names]
    missing = sorted(set(table_names) - set(insert_order))
    if missing:
        logger.warning("Table(s) absent from the target schema, skipped: %s", ", ".join(missing))

    copied: Dict[str, int] = {}

    with source.connect() as source_connection:
        if dry_run:
            for name in insert_order:
                count = source_connection.execute(select(func.count()).select_from(source_metadata.tables[name])).scalar() or 0
                copied[name] = int(count)
            return copied

        with target.begin() as target_connection:
            _disable_foreign_key_triggers(target_connection)
            target_tables = [target_metadata.tables[name] for name in insert_order]

            if mode == "replace":
                _truncate_target(target_connection, target_tables)

            for name in insert_order:
                source_table = source_metadata.tables[name]
                target_table = target_metadata.tables[name]
                rows = _fetch_rows(source_connection, source_table)
                if not rows:
                    copied[name] = 0
                    continue

                # psycopg reports no usable rowcount for a batched INSERT, so
                # skip-existing mode measures the real change with row counts.
                rows_before = int(target_connection.execute(select(func.count()).select_from(target_table)).scalar() or 0)

                for batch in _chunks(rows, batch_size):
                    payload = [dict(row) for row in batch]
                    if mode == "skip-existing":
                        # Let the server drop rows whose primary key is taken.
                        statement = postgres_insert(target_table).on_conflict_do_nothing()
                    else:
                        statement = target_table.insert()
                    target_connection.execute(statement, payload)

                if mode == "skip-existing":
                    rows_after = int(target_connection.execute(select(func.count()).select_from(target_table)).scalar() or 0)
                    copied[name] = rows_after - rows_before
                else:
                    copied[name] = len(rows)
                logger.info("Copied %-45s %6d row(s)", name, copied[name])

            reset = _reset_sequences(target_connection, target_tables)
            if reset:
                logger.info("Reset %d sequence(s): %s", len(reset), ", ".join(reset))

    return copied


def verify_tables(source: Engine, target: Engine, table_names: Sequence[str], mode: str) -> List[str]:
    """Compare the source and target content of the selected tables.

    Args:
        source: Engine bound to the SQLite database.
        target: Engine bound to the PostgreSQL database.
        table_names: Tables to compare.
        mode: ``replace`` requires exact equality. ``skip-existing`` requires the
            target to hold every source row and allows extra target rows.

    Returns:
        List[str]: One human-readable description per mismatch.
    """
    source_metadata = _reflect(source)
    target_metadata = _reflect(target)
    problems: List[str] = []

    with source.connect() as source_connection, target.connect() as target_connection:
        for name in sorted(table_names):
            source_rows = _fetch_rows(source_connection, source_metadata.tables[name])
            target_rows = _fetch_rows(target_connection, target_metadata.tables[name])

            if mode == "replace" and len(source_rows) != len(target_rows):
                problems.append(f"{name}: source has {len(source_rows)} row(s), target has {len(target_rows)}")
                continue

            source_fingerprints = sorted(_row_fingerprint(row) for row in source_rows)
            target_fingerprints = sorted(_row_fingerprint(row) for row in target_rows)

            if mode == "skip-existing":
                missing = _multiset_difference(source_fingerprints, target_fingerprints)
                if missing:
                    problems.append(f"{name}: {len(missing)} source row(s) are absent from the target")
                    problems.append(f"{name}: first missing row {missing[0][:200]}")
                continue

            if source_fingerprints != target_fingerprints:
                only_source = _multiset_difference(source_fingerprints, target_fingerprints)
                only_target = _multiset_difference(target_fingerprints, source_fingerprints)
                problems.append(f"{name}: {len(only_source)} row(s) only in source, {len(only_target)} row(s) only in target")
                if only_source:
                    problems.append(f"{name}: first source-only row {only_source[0][:200]}")
                if only_target:
                    problems.append(f"{name}: first target-only row {only_target[0][:200]}")

    return problems


def _multiset_difference(left: Sequence[str], right: Sequence[str]) -> List[str]:
    """Return the entries of one sorted list that the other lacks.

    Args:
        left: Sorted fingerprints to test.
        right: Sorted fingerprints to test against.

    Returns:
        List[str]: Entries of ``left`` whose multiplicity exceeds ``right``.
    """
    remaining: Dict[str, int] = {}
    for item in right:
        remaining[item] = remaining.get(item, 0) + 1
    difference: List[str] = []
    for item in left:
        if remaining.get(item, 0) > 0:
            remaining[item] -= 1
        else:
            difference.append(item)
    return difference


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Argument list, defaulting to sys.argv[1:].

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Copy ContextForge data from SQLite to PostgreSQL.")
    parser.add_argument("--source", default=os.environ.get("SQLITE_DATABASE_URL", "sqlite:///./mcp.db"), help="Source SQLite URL (default: sqlite:///./mcp.db)")
    parser.add_argument("--target", default=None, help="Target PostgreSQL URL (default: $DATABASE_URL, then .env)")
    parser.add_argument("--mode", choices=("replace", "skip-existing"), default="replace", help="How to treat existing target rows (default: replace)")
    parser.add_argument("--tables", default=None, help="Comma-separated subset of tables (default: every shared table)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"Rows per INSERT (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--dry-run", action="store_true", help="Report row counts without writing")
    parser.add_argument("--verify-only", action="store_true", help="Compare the databases without writing")
    parser.add_argument("--no-verify", action="store_true", help="Skip the post-copy comparison")
    parser.add_argument("--yes", action="store_true", help="Confirm the destructive replace mode")
    parser.add_argument("--force", action="store_true", help="Continue even when the Alembic revisions differ")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"), help="Logging verbosity (default: INFO)")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the migration.

    Args:
        argv: Argument list, defaulting to sys.argv[1:].

    Returns:
        int: Process exit code.
    """
    args = _parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")

    if not args.source.startswith("sqlite"):
        logger.error("--source must be a SQLite URL, got: %s", args.source)
        return 1

    target_url = _resolve_target_url(args.target)

    if args.mode == "replace" and not args.dry_run and not args.verify_only and not args.yes:
        logger.error("Mode 'replace' truncates the target tables. Re-run with --yes to confirm, or use --mode skip-existing.")
        return 1

    source_engine = create_engine(args.source)
    target_engine = create_engine(target_url)

    try:
        with source_engine.connect() as source_connection, target_engine.connect() as target_connection:
            source_revision = _alembic_revision(source_connection)
            target_revision = _alembic_revision(target_connection)
        logger.info("Source revision: %s", source_revision)
        logger.info("Target revision: %s", target_revision)
        if source_revision != target_revision and not args.force:
            logger.error("Revisions differ. Run 'alembic upgrade head' on both databases, or pass --force to override.")
            return 1

        source_tables = set(_reflect(source_engine).tables)
        target_tables = set(_reflect(target_engine).tables)
        shared = sorted((source_tables & target_tables) - SKIP_TABLES)
        if args.tables:
            requested = [name.strip() for name in args.tables.split(",") if name.strip()]
            unknown = sorted(set(requested) - set(shared))
            if unknown:
                logger.error("--tables names table(s) absent from one database: %s", ", ".join(unknown))
                return 1
            shared = requested
        if not shared:
            logger.error("No shared tables to copy.")
            return 1
        logger.info("Tables in scope: %d", len(shared))

        if args.verify_only:
            problems = verify_tables(source_engine, target_engine, shared, args.mode)
            if problems:
                for problem in problems:
                    logger.error("MISMATCH %s", problem)
                return 2
            logger.info("Verification passed for %d table(s)", len(shared))
            return 0

        copied = copy_tables(source_engine, target_engine, shared, args.mode, args.batch_size, args.dry_run)
        if args.dry_run:
            logger.info("Dry run: %d row(s) across %d table(s) would be copied", sum(copied.values()), len(copied))
            for name in sorted(copied):
                logger.info("  %-45s %6d row(s)", name, copied[name])
            return 0

        logger.info("Copied %d row(s) across %d table(s)", sum(copied.values()), len(copied))

        if args.no_verify:
            return 0

        problems = verify_tables(source_engine, target_engine, shared, args.mode)
        if problems:
            for problem in problems:
                logger.error("MISMATCH %s", problem)
            return 2
        logger.info("Verification passed for %d table(s)", len(shared))
        return 0
    except SQLAlchemyError as exc:
        logger.error("Migration failed: %s", exc)
        return 1
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
