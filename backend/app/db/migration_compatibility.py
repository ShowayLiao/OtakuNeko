"""Strict adoption checks for the immutable A-L1-03 migration snapshot."""

import re
from collections.abc import Sequence
from typing import NoReturn

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.db.migration_snapshot import BUSINESS_TABLES, METADATA, POSTGRES_CHECKS


AGENT_TABLE_GROUPS = (
    ("agent_memory",),
    ("agent_task_def", "agent_task_run"),
    ("agent_trace", "trace_event"),
    ("agent_run", "agent_invocation", "agent_run_event"),
)


def _reject() -> NoReturn:
    # Do not echo rows, database URLs or arbitrary reflected schema into logs.
    raise RuntimeError("unsupported_business_schema: explicit migration required")


def _type_sql(column_type: sa.types.TypeEngine, connection: Connection) -> str:
    if connection.dialect.name == "postgresql" and isinstance(column_type, sa.REAL):
        return "REAL"
    if connection.dialect.name == "postgresql" and isinstance(column_type, sa.Float):
        # PostgreSQL FLOAT without precision is FLOAT(53), reflected as DOUBLE.
        return (
            "DOUBLE PRECISION"
            if column_type.precision is None or column_type.precision > 24
            else "REAL"
        )
    return str(column_type.compile(dialect=connection.dialect)).upper()


# Preserve quoted values exactly; normalize only unquoted SQL tokens.
_CHECK_TOKENS = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|"
    r"[A-Za-z_][A-Za-z_0-9$]*|[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?|"
    r"<>|!=|<=|>=|::|[^\s]"
)


def _normalized_check(value: str) -> tuple[str, ...]:
    return tuple(
        token if token[0] in "'\"`" else token.lower()
        for token in _CHECK_TOKENS.findall(value)
    )


# SQLite records a UNIQUE constraint's conflict strategy only in the stored
# CREATE TABLE text; reflection reports the columns without the clause.
_SQLITE_DDL_TOKENS = re.compile(
    r"--[^\r\n]*|/\*[\s\S]*?\*/|"
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^]]*\]|"
    r"[A-Za-z_][A-Za-z_0-9$]*|[^\s]"
)
_SQLITE_DEFAULT_CONFLICT = "ABORT"


def _sqlite_unique_conflicts(table_sql: str) -> list[str]:
    """Read UNIQUE strategies without interpreting quoted text or comments."""
    tokens = [
        token.upper()
        for token in _SQLITE_DDL_TOKENS.findall(table_sql)
        if not token.startswith(("--", "/*"))
    ]
    conflicts = []
    for index, token in enumerate(tokens):
        if token != "UNIQUE":
            continue
        position = index + 1
        if position < len(tokens) and tokens[position] == "(":
            depth = 0
            while position < len(tokens):
                if tokens[position] == "(":
                    depth += 1
                elif tokens[position] == ")":
                    depth -= 1
                    if depth == 0:
                        position += 1
                        break
                position += 1
        if tokens[position : position + 2] == ["ON", "CONFLICT"]:
            conflicts.append(tokens[position + 2])
        else:
            conflicts.append(_SQLITE_DEFAULT_CONFLICT)
    return conflicts


def _validate_primary_key_generation(
    connection: Connection, expected: sa.Table, actual_columns: dict
) -> None:
    columns = list(expected.primary_key.columns)
    if len(columns) != 1:
        return
    column = columns[0]
    if not isinstance(column.type, sa.Integer) or column.autoincrement is False:
        return
    if connection.dialect.name == "sqlite":
        # A ROWID-alias INTEGER PRIMARY KEY has no separate primary-key index.
        # WITHOUT ROWID and PRIMARY KEY DESC cannot generate the expected id.
        quoted = connection.dialect.identifier_preparer.quote_identifier(expected.name)
        indexes = connection.exec_driver_sql(
            f"PRAGMA main.index_list({quoted})"
        ).mappings()
        if any(index["origin"] == "pk" for index in indexes):
            _reject()
    elif connection.dialect.name == "postgresql":
        actual = actual_columns[column.name]
        if not actual.get("identity") and actual.get("autoincrement") is not True:
            _reject()


def validate_table(connection: Connection, name: str) -> None:
    """Accept an existing table only when its structural contract matches."""
    inspector = sa.inspect(connection)
    expected = METADATA.tables[name]
    actual_columns = {column["name"]: column for column in inspector.get_columns(name)}
    if set(actual_columns) != set(expected.columns.keys()):
        _reject()
    for column in expected.columns:
        actual = actual_columns[column.name]
        if actual["nullable"] != column.nullable:
            _reject()
        if _type_sql(actual["type"], connection) != _type_sql(column.type, connection):
            _reject()
        # The snapshot declares plain columns only. A generated column rejects
        # ordinary inserts, so adopting one breaks every ORM write.
        if actual.get("computed") is not None:
            _reject()
        if connection.dialect.name == "postgresql" and isinstance(column.type, sa.Enum):
            actual_enum = actual["type"]
            if (
                not isinstance(actual_enum, sa.Enum)
                or actual_enum.enums != column.type.enums
            ):
                _reject()
            if (actual_enum.schema or inspector.default_schema_name) != (
                column.type.schema or inspector.default_schema_name
            ):
                _reject()
    if tuple(inspector.get_pk_constraint(name)["constrained_columns"]) != tuple(
        column.name for column in expected.primary_key.columns
    ):
        _reject()
    _validate_primary_key_generation(connection, expected, actual_columns)
    reflected_indexes = [
        index
        for index in inspector.get_indexes(name)
        if not index.get("duplicates_constraint")
    ]
    # The immutable snapshot contains only unconditional indexes.
    if any(
        (index.get("dialect_options") or {}).get(f"{connection.dialect.name}_where")
        is not None
        for index in reflected_indexes
    ):
        _reject()
    actual_indexes = {
        (index["name"], tuple(index["column_names"]), bool(index["unique"]))
        for index in reflected_indexes
        # PostgreSQL reports UNIQUE constraints again as backing indexes.
        # Those constraints are compared separately below.
        if not index.get("duplicates_constraint")
    }
    expected_indexes = {
        (index.name, tuple(column.name for column in index.columns), index.unique)
        for index in expected.indexes
    }
    if actual_indexes != expected_indexes:
        _reject()
    actual_unique = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(name)
    }
    expected_unique = {
        tuple(column.name for column in constraint.columns)
        for constraint in expected.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    if actual_unique != expected_unique:
        _reject()
    if connection.dialect.name == "sqlite":
        # The snapshot pins every unique constraint to SQLite's implicit
        # resolution, so a declared strategy that resolves duplicate writes any
        # other way is a different constraint even when the columns match.
        table_sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,),
        ).scalar()
        if table_sql is None:
            _reject()
        if any(
            action != _SQLITE_DEFAULT_CONFLICT
            for action in _sqlite_unique_conflicts(table_sql)
        ):
            _reject()
    actual_foreign_keys = {
        (
            tuple(key["constrained_columns"]),
            key.get("referred_schema") or inspector.default_schema_name,
            key["referred_table"],
            tuple(key["referred_columns"]),
            (key.get("options") or {}).get("ondelete"),
        )
        for key in inspector.get_foreign_keys(name)
    }
    expected_foreign_keys = {
        (
            tuple(element.parent.name for element in key.elements),
            key.elements[0].column.table.schema or inspector.default_schema_name,
            key.elements[0].column.table.name,
            tuple(element.column.name for element in key.elements),
            key.ondelete,
        )
        for key in expected.foreign_key_constraints
    }
    if actual_foreign_keys != expected_foreign_keys:
        _reject()

    actual_checks = {
        _normalized_check(constraint["sqltext"])
        for constraint in inspector.get_check_constraints(name)
    }
    expected_checks = {
        _normalized_check(str(constraint.sqltext))
        for constraint in expected.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    if connection.dialect.name == "postgresql" and name in POSTGRES_CHECKS:
        expected_checks = {_normalized_check(value) for value in POSTGRES_CHECKS[name]}
    if actual_checks != expected_checks:
        _reject()


def bootstrap_business_schema(connection: Connection) -> None:
    """Validate everything already present before creating any baseline table."""
    existing = set(sa.inspect(connection).get_table_names())
    if "user" in existing:
        _reject()
    for group in AGENT_TABLE_GROUPS:
        present = existing.intersection(group)
        if present and present != set(group):
            _reject()
    for name in sorted(existing.intersection(METADATA.tables)):
        validate_table(connection, name)
    for table in METADATA.sorted_tables:
        if table.name in BUSINESS_TABLES and table.name not in existing:
            table.create(connection)


def adopt_existing_tables(connection: Connection, names: Sequence[str]) -> bool:
    """Reuse a complete compatible group, rejecting partial/mismatched groups."""
    existing = set(sa.inspect(connection).get_table_names()).intersection(names)
    if not existing:
        return False
    if existing != set(names):
        _reject()
    for name in names:
        validate_table(connection, name)
    return True


def has_current_business_schema(connection: Connection) -> bool:
    """The bootstrap owns current business columns and indexes through rollback."""
    existing = set(sa.inspect(connection).get_table_names())
    if "users" not in existing:
        return False
    for name in BUSINESS_TABLES:
        if name not in existing:
            _reject()
        validate_table(connection, name)
    return True
