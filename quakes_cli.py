#!/usr/bin/env python3
"""Command line interface for the earthquake catalog client.

The entire CLI is ``auto_cli(EarthquakeCatalog)``. jsonargparse reads the
signatures and docstrings of the class to derive the options, the subcommands
and the help. The only thing left to do here is to print whatever the called
method returned, in a way that suits its type.
"""

import json
import sys
from dataclasses import fields, is_dataclass
from datetime import date, datetime

from quakes_client import CatalogError, EarthquakeCatalog

from jsonargparse import auto_cli
from jsonargparse.typing import register_type

# Teach jsonargparse how to read and write the one type it does not know about,
# so that the client can keep using dates in its signatures.
register_type(date, serializer=date.isoformat, deserializer=date.fromisoformat)


def render(result) -> str:
    """Render a value returned by a client method as text for a terminal.

    Args:
        result: Whatever the called method returned.

    Returns:
        Scalars as they are, lists of records as an aligned table, and anything
        else as indented JSON.
    """
    if isinstance(result, (str, int, float)):
        return str(result)
    if isinstance(result, list) and result and is_dataclass(result[0]):
        return render_table(result)
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


def render_table(records: list) -> str:
    """Render a list of dataclass instances as a table with aligned columns.

    Args:
        records: The instances to render, all of the same dataclass.

    Returns:
        A header row followed by one row per instance.
    """
    columns = [field.name for field in fields(records[0])]
    rows = [columns] + [[cell(getattr(record, column)) for column in columns] for record in records]
    widths = [max(len(row[index]) for row in rows) for index in range(len(columns))]
    return "\n".join("  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip() for row in rows)


def cell(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if isinstance(value, datetime) else str(value)


if __name__ == "__main__":
    try:
        print(render(auto_cli(EarthquakeCatalog)))
    except CatalogError as ex:
        sys.exit(f"error: {ex}")
