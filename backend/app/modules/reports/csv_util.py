from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence


def escape_row(cells: Sequence[object]) -> list[str]:
    return ["" if c is None else str(c) for c in cells]


def build_csv(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(list(headers))
    for row in rows:
        writer.writerow(escape_row(row))
    return buf.getvalue()