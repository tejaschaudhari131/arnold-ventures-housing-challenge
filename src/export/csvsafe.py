# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Stop spreadsheet formulas in exported text cells.

A cell whose text starts with =, +, -, @, tab, or carriage return is executed
by Excel and Sheets. Plain numbers, including negatives, stay numbers.
"""

from __future__ import annotations

import re
from typing import Any

_FORMULA = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"^[+\-]?(\d+(\.\d*)?|\.\d+)([eE][+\-]?\d+)?$")


def csv_cell(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    text = str(value)
    if text.startswith(_FORMULA) and not _NUMBER.match(text):
        return "'" + text
    return text
