"""Opt-in check of a dedicated Phoenix SQLite database after the documented run."""

import json
import os
import sqlite3
from collections import Counter
from pathlib import Path

import pytest


@pytest.mark.skipif(not os.getenv("TFB_PHOENIX_DB"), reason="requires a dedicated Phoenix run")
def test_harbor_session_is_stored_in_phoenix():
    database = Path(os.environ["TFB_PHOENIX_DB"]).resolve()
    with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(
            "SELECT trace_rowid, span_id, parent_id, span_kind, status_code, attributes FROM spans"
        )]
    for row in rows:
        row["attributes"] = json.loads(row["attributes"])
    assert len(rows) == 15
    assert len({row["trace_rowid"] for row in rows}) == 1
    by_id = {row["span_id"]: row for row in rows}
    roots = [row for row in rows if row["parent_id"] is None]
    assert len(roots) == 1 and roots[0]["span_kind"] == "CHAIN"
    tools = [row for row in rows if row["span_kind"] == "TOOL"]
    assert len(tools) == 6
    assert Counter(row["status_code"] for row in tools) == {"OK": 5, "ERROR": 1}
    assert all(by_id[row["parent_id"]]["span_kind"] == "AGENT" and
               by_id[row["parent_id"]]["parent_id"] == roots[0]["span_id"] for row in tools)
    failed = next(row for row in tools if row["status_code"] == "ERROR")
    assert failed["attributes"]["tool"]["id"] == "tool-call-0003"
    assert all("input" not in row["attributes"] and "output" not in row["attributes"]
               for row in rows)
