# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Minimal ESRI shapefile (.shp + .dbf) reader and line simplifier.

Only polygon shapes (type 5) are supported, which is all the Census
cartographic boundary files use. Standard library only.
"""

from __future__ import annotations

import struct
from typing import Any

Point = tuple[float, float]
Ring = list[Point]


def read_dbf(blob: bytes) -> list[dict[str, str]]:
    """Return each dBASE record as a dict of stripped strings."""
    count = struct.unpack("<I", blob[4:8])[0]
    header_len, record_len = struct.unpack("<HH", blob[8:12])
    fields: list[tuple[str, int]] = []
    offset = 32
    while blob[offset] != 0x0D:
        raw_name = blob[offset : offset + 11].split(b"\x00", 1)[0]
        length = blob[offset + 16]
        fields.append((raw_name.decode("latin1"), length))
        offset += 32
    records: list[dict[str, str]] = []
    position = header_len
    for _ in range(count):
        row = blob[position : position + record_len]
        position += record_len
        if not row or row[0:1] == b"*":
            continue
        cursor = 1
        record: dict[str, str] = {}
        for name, length in fields:
            record[name] = row[cursor : cursor + length].decode("latin1").strip()
            cursor += length
        records.append(record)
    return records


def read_polygons(blob: bytes) -> list[list[Ring]]:
    """Return a list of shapes; each shape is a list of rings of (lon, lat)."""
    shapes: list[list[Ring]] = []
    position = 100
    size = len(blob)
    while position + 8 <= size:
        _number, words = struct.unpack(">ii", blob[position : position + 8])
        content = blob[position + 8 : position + 8 + words * 2]
        position += 8 + words * 2
        shape_type = struct.unpack("<i", content[0:4])[0]
        if shape_type == 0:
            shapes.append([])
            continue
        if shape_type != 5:
            raise ValueError(f"Unsupported shape type {shape_type}")
        num_parts, num_points = struct.unpack("<ii", content[36:44])
        parts = list(struct.unpack(f"<{num_parts}i", content[44 : 44 + 4 * num_parts]))
        coords_start = 44 + 4 * num_parts
        flat = struct.unpack(f"<{2 * num_points}d", content[coords_start : coords_start + 16 * num_points])
        points = [(flat[2 * i], flat[2 * i + 1]) for i in range(num_points)]
        parts.append(num_points)
        shapes.append([points[parts[i] : parts[i + 1]] for i in range(num_parts)])
    return shapes


def _perpendicular(point: Point, start: Point, end: Point) -> float:
    (x, y), (x1, y1), (x2, y2) = point, start, end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / (dx * dx + dy * dy) ** 0.5


def simplify(points: Ring, tolerance: float) -> Ring:
    """Douglas–Peucker, iterative so long county borders cannot hit the recursion limit."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        best, index = 0.0, -1
        for i in range(first + 1, last):
            distance = _perpendicular(points[i], points[first], points[last])
            if distance > best:
                best, index = distance, i
        if index >= 0 and best > tolerance:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [point for point, kept in zip(points, keep) if kept]


def ring_area(ring: Ring) -> float:
    return 0.5 * abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1])))


def simplify_shape(rings: list[Ring], tolerance: float, digits: int = 4) -> list[list[list[float]]]:
    """Simplify every ring, drop slivers, and round to `digits` decimals."""
    out: list[list[list[float]]] = []
    for ring in rings:
        reduced = simplify(ring, tolerance)
        if len(reduced) < 4 or ring_area(reduced) < tolerance * tolerance:
            continue
        out.append([[round(x, digits), round(y, digits)] for x, y in reduced])
    if not out and rings:
        largest = max(rings, key=ring_area)
        out.append([[round(x, digits), round(y, digits)] for x, y in largest])
    return out


def features(shp: bytes, dbf: bytes, keep: Any, tolerance: float) -> list[dict[str, Any]]:
    """Join shapes to records and keep those where keep(record) is true."""
    records = read_dbf(dbf)
    shapes = read_polygons(shp)
    if len(records) != len(shapes):
        raise ValueError(f"{len(records)} dbf records but {len(shapes)} shapes")
    result = []
    for record, rings in zip(records, shapes):
        if not keep(record):
            continue
        result.append({"properties": record, "rings": simplify_shape(rings, tolerance)})
    return result
