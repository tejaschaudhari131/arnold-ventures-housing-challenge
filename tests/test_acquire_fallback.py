# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""The public-data refresh must not crash on the gazetteer unpack, and any
failure must fall back to data/sample the way the README describes.
"""

from __future__ import annotations

import io
import os
import stat
import subprocess
import zipfile
from pathlib import Path

from src.data import acquire

ROOT = Path(__file__).resolve().parents[1]


def _gazetteer_zip() -> bytes:
    text = (
        "GEOID\tNAME\tALAND_SQMI\tINTPTLAT\tINTPTLONG\n"
        "42003\tAllegheny\t730.0\t40.4680\t-79.9810\n"
        "09001\tFairfield\t625.0\t41.2300\t-73.3700\n"
        "99999\tIgnore Me\t1.0\t0.0\t0.0\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("2024_Gaz_counties_national.txt", text)
    return buffer.getvalue()


def test_bound_load_land_unpacks_land_and_points(monkeypatch):
    """Regression: load_land was rebound to a function that returned only land.

    ``land, points = load_land()`` then raised ValueError: too many values to
    unpack (expected 2) and scripts/get_data.sh exited 1.
    """
    monkeypatch.setattr(acquire, "fetch_bytes", lambda _url: _gazetteer_zip())
    previous = getattr(acquire.load_land, "_names", None)
    try:
        land, points = acquire.load_land()
        assert land["42003"] == 730.0
        assert land["09001"] == 625.0
        assert "99999" not in land
        by_fips = {point["fips"]: point for point in points}
        assert by_fips["42003"]["name"] == "Allegheny"
        assert by_fips["42003"]["lat"] == 40.468
        assert by_fips["09001"]["state"] == "CT"
        assert acquire._county_name("42003", land) == "Allegheny"
    finally:
        if previous is None:
            if hasattr(acquire.load_land, "_names"):
                del acquire.load_land._names
        else:
            acquire.load_land._names = previous


def test_main_falls_back_on_unexpected_unpack_error(monkeypatch, capsys):
    def boom():
        raise ValueError("too many values to unpack (expected 2)")

    monkeypatch.setattr(acquire, "build_states", boom)
    assert acquire.main([]) == 2
    err = capsys.readouterr().err
    assert "too many values to unpack" in err
    assert "Falling back" in err


def test_get_data_sh_falls_back_on_any_nonzero_exit(tmp_path):
    fake = tmp_path / "python"
    fake.write_text(
        "#!/bin/sh\n"
        "echo 'ValueError: too many values to unpack (expected 2)' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = os.environ.copy()
    env["STATEFRAME_PYTHON"] = str(fake)
    proc = subprocess.run(
        ["bash", "scripts/get_data.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "Using the committed benchmark" in proc.stdout
    assert "exit 1" in proc.stdout
