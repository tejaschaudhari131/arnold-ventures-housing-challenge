# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Stdlib HTTP server for the simulator.

Routes are a fixed map. Nothing the client sends is joined onto a filesystem
path. JSON bodies are size-capped. Assumption overrides are validated and
clamped by the assumption loader before they reach the equations.
"""

from __future__ import annotations

import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.bundle import load_bundle
from src.data.schema import CHALLENGE_STATES, ROOT
from src.export.report import simulate_many, to_csv, to_json, to_markdown
from src.model.assumptions import AssumptionError
from src.model.case_study import build_case_study
from src.model.crossval import cross_validate_state, cross_validate_tier1
from src.model.engine import REFORM_IDS, simulate_state
from src.model.sensitivity import monte_carlo, tornado

COUNTY_POINTS = ROOT / "data" / "sample" / "county_points.json"

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/tokens.css": ("tokens.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/lab": ("lab.html", "text/html; charset=utf-8"),
    "/lab.html": ("lab.html", "text/html; charset=utf-8"),
    "/lab.css": ("lab.css", "text/css; charset=utf-8"),
    "/lab.js": ("lab.js", "text/javascript; charset=utf-8"),
}
MAX_BODY = 64_000
_ERROR_LIMIT = 160
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
)
_PERMISSIONS = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=()"
)


def public_error(message: str) -> str:
    """Short 400 text. User input is not repeated."""
    cleaned = []
    for ch in " ".join(str(message).split()):
        if ch in "<>\"'`":
            continue
        if 32 <= ord(ch) < 127:
            cleaned.append(ch)
    text = "".join(cleaned).strip()
    if len(text) > _ERROR_LIMIT:
        text = text[:_ERROR_LIMIT].rstrip()
    return text or "Bad request"


def parse_request_int(raw: Any, low: int, high: int, label: str) -> int:
    """Accept a JSON int or an ASCII digit string inside [low, high].

    Unicode digits such as superscript ² and Arabic-Indic ٢٠ are not integers
    here. ``str.isdigit`` is true for both, and ``int`` then raises or would
    misread them. The message names the range and does not repeat the input.
    """
    message = f"{label} must be an integer from {low} to {high}."
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise AssumptionError(message)
    if isinstance(raw, str):
        if not (raw.isascii() and raw.isdigit()):
            raise AssumptionError(message)
        try:
            number = int(raw)
        except ValueError:
            raise AssumptionError(message) from None
    else:
        number = raw
    if number < low or number > high:
        raise AssumptionError(message)
    return number


def finite_draws(raw: Any, low: int, high: int) -> int:
    return parse_request_int(raw, low, high, "draws")


_VIEW_LABELS = {
    "baseline": "the baseline",
    "adu": "ADUs",
    "missing_middle": "missing middle",
    "tod": "transit-oriented density",
    "parking": "parking reform",
    "fees": "the fee cut",
    "combined": "the active package",
}


def _sensitivity_label(scenario: str) -> str:
    name = _VIEW_LABELS.get(scenario, "the selected view")
    if scenario == "combined":
        shown = "Showing the active package"
    else:
        shown = f"Showing {name}"
    return (
        f"{shown}. An overridden Monte Carlo parameter becomes the mode of its triangle "
        "and still varies across draws."
    )


def read_doc(path: str) -> bytes | None:
    """Serve one committed markdown file. Nothing else under /docs/."""
    name = path.removeprefix("/docs/")
    if not name or "/" in name or "\\" in name or name.startswith(".") or not name.endswith(".md"):
        return None
    docs = (ROOT / "docs").resolve()
    target = (docs / name).resolve()
    if target.parent != docs or not target.is_file():
        return None
    return target.read_bytes()
# Static files and the fingerprinted Lab results/geo payloads. HTML is
# included because the injected notes change only when the build changes.
# HTML is rebuilt on each deploy (fee note, engine gap, build stamp). A day-long
# CDN cache would keep that copy after a data refresh. Versioned asset URLs
# (?v=<sha>) and the fingerprinted Lab results may stay cached.
HTML_CACHE = "public, max-age=60, s-maxage=60, stale-while-revalidate=60"
ASSET_CACHE = "public, max-age=300, s-maxage=86400"
HTML_PATHS = {"/", "/index.html", "/lab", "/lab.html"}


def _state_catalog(fixtures: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = []
    for code in CHALLENGE_STATES:
        state = fixtures["states"][code]
        catalog.append(
            {
                "code": code,
                "name": state["name"],
                "tier": state["tier"],
                "completeness": state.get("completeness", 0),
                "housing_units": state["housing_units"],
                "median_value": state["median_value"],
            }
        )
    return catalog


class App:
    def __init__(self) -> None:
        self.fixtures, self.assumptions = load_bundle()

    def states(self) -> dict[str, Any]:
        return {"states": _state_catalog(self.fixtures)}

    def assumption_catalog(self, state: str) -> dict[str, Any]:
        self._check_state(state)
        meta = self.assumptions.states[state]
        return {
            "state": state,
            "legal_note": meta.get("legal_note", ""),
            "parameters": self.assumptions.ui_parameters(state),
        }

    def simulate(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._check_state(str(payload.get("state", "PA")))
        overrides = payload.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise AssumptionError("overrides must be an object")
        parcel_mode = payload.get("parcel_mode", "observed")
        resolution = payload.get("resolution", "county")
        if parcel_mode not in {"observed", "imputed"}:
            raise AssumptionError("parcel_mode must be observed or imputed")
        if resolution not in {"county", "state"}:
            raise AssumptionError("resolution must be county or state")
        return simulate_state(
            self.fixtures,
            self.assumptions,
            state,
            overrides,
            parcel_mode=parcel_mode,
            resolution=resolution,
            reform_weights=self._reforms(payload.get("reforms")),
        )

    def case_study(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        overrides = payload.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise AssumptionError("overrides must be an object")
        return build_case_study(
            self.fixtures,
            self.assumptions,
            overrides,
            reform_weights=self._reforms(payload.get("reforms")),
        )

    def map_points(self) -> dict[str, Any]:
        return json.loads(COUNTY_POINTS.read_text(encoding="utf-8"))

    def sensitivity(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._check_state(str(payload.get("state", "PA")))
        scenario = str(payload.get("scenario", "combined"))
        self._check_scenario(scenario)
        draws = finite_draws(payload["draws"], 20, 400) if "draws" in payload else 80
        overrides = payload.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise AssumptionError("overrides must be an object.")
        reforms = self._reforms(payload.get("reforms"))
        return {
            "tornado": tornado(
                self.fixtures,
                self.assumptions,
                state,
                scenario,
                overrides=overrides,
                reform_weights=reforms,
            ),
            "monte_carlo": monte_carlo(
                self.fixtures,
                self.assumptions,
                state,
                scenario,
                draws=draws,
                overrides=overrides,
                reform_weights=reforms,
            ),
            "scenario_label": _sensitivity_label(scenario),
            "reference": False,
        }

    def crossval(self, payload: dict[str, Any]) -> dict[str, Any]:
        scope = str(payload.get("scope", "tier1"))
        draws = finite_draws(payload["draws"], 20, 200) if "draws" in payload else 40
        if scope == "tier1":
            return cross_validate_tier1(self.fixtures, self.assumptions, draws=draws)
        state = self._check_state(str(payload.get("state", "CT")))
        return {"states": {state: cross_validate_state(self.fixtures, self.assumptions, state, draws=draws)}}

    def lab_results(self, state: str) -> dict[str, Any]:
        from src.lab.explain import locked_results

        return locked_results(state)

    def lab_geo(self, state: str) -> dict[str, Any]:
        from src.lab.explain import geo

        return geo(state)

    def lab_assumptions(self) -> dict[str, Any]:
        from src.lab.explain import assumption_catalog

        return assumption_catalog()

    def lab_why(self, payload: dict[str, Any]) -> dict[str, Any]:
        from src.lab.explain import clamp_overrides, why_county

        return why_county(
            str(payload.get("state", "PA")),
            str(payload.get("county", "Allegheny")),
            str(payload.get("scenario", "adu")),
            clamp_overrides(payload.get("overrides")),
            payload.get("reforms"),
        )

    def lab_recompute(self, payload: dict[str, Any]) -> dict[str, Any]:
        from src.lab.explain import _selected_reforms, clamp_overrides, recompute

        if "reforms" in payload and payload.get("reforms") is not None:
            _selected_reforms(payload.get("reforms"))
        county = payload.get("county")
        return recompute(
            str(payload.get("state", "PA")),
            clamp_overrides(payload.get("overrides")),
            str(county) if county else None,
        )

    def lab_export(
        self,
        state: str,
        fmt: str,
        county: str | None,
        overrides: dict[str, Any] | None,
        reforms: Any = None,
    ) -> tuple[bytes, str, str]:
        from src.lab.explain import clamp_overrides, export_brief

        selected: list[str] | None
        if reforms is None:
            selected = None
        elif isinstance(reforms, list):
            selected = [str(item) for item in reforms]
        else:
            raise AssumptionError("reforms must be a list.")
        return export_brief(
            state,
            fmt,
            county,
            clamp_overrides(overrides) if overrides else None,
            selected,
        )

    def adu_compare(self, state: str = "PA") -> dict[str, Any]:
        from src.adu_fee_note import comparison

        return comparison(self._check_state(state))

    def export(
        self,
        state: str,
        fmt: str,
        overrides: dict[str, Any] | None = None,
        reforms: Any = None,
    ) -> tuple[bytes, str, str]:
        if fmt not in {"csv", "json", "md"}:
            raise AssumptionError("format must be csv, json, or md")
        if overrides is not None and not isinstance(overrides, dict):
            raise AssumptionError("overrides must be an object.")
        weights = self._reforms(reforms) if reforms is not None else None
        custom = bool(overrides) or weights is not None
        if state == "all":
            if custom:
                raise AssumptionError("A custom export covers one state.")
            results = simulate_many(self.fixtures, self.assumptions)
            stem = "stateframe-all-states"
            scenario = None
        else:
            code = self._check_state(state)
            results = simulate_many(
                self.fixtures,
                self.assumptions,
                [code],
                overrides=overrides,
                reform_weights=weights,
            )
            stem = f"stateframe-{code}"
            scenario = {"state": code, "overrides": overrides or {}, "reforms": weights} if custom else None
        note = ""
        if scenario:
            note = "This export uses the posted assumption overrides and reform mix, not the published defaults."
        if fmt == "csv":
            body, mime = to_csv(results), "text/csv; charset=utf-8"
        elif fmt == "md":
            body, mime = to_markdown(results, note), "text/markdown; charset=utf-8"
        else:
            body, mime = to_json(results, scenario), "application/json; charset=utf-8"
        return body.encode("utf-8"), mime, f"{stem}.{fmt if fmt != 'md' else 'md'}"

    def _check_state(self, state: str) -> str:
        code = state.strip().upper()
        if code not in self.fixtures["states"]:
            raise AssumptionError("Unknown state.")
        return code

    @staticmethod
    def _reforms(raw: Any) -> dict[str, float] | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise AssumptionError("reforms must be an object")
        weights: dict[str, float] = {}
        for key, value in raw.items():
            if key not in REFORM_IDS:
                raise AssumptionError("Unknown reform.")
            if isinstance(value, bool):
                weights[key] = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                if not math.isfinite(float(value)):
                    raise AssumptionError("Reform weight must be a finite number.")
                weights[key] = float(value)
            elif isinstance(value, dict):
                turned_on = bool(value.get("on", True))
                try:
                    weight = float(value.get("weight", 1.0))
                except (TypeError, ValueError) as exc:
                    raise AssumptionError("Reform weight must be a finite number.") from exc
                if not math.isfinite(weight):
                    raise AssumptionError("Reform weight must be a finite number.")
                weights[key] = weight if turned_on else 0.0
            else:
                raise AssumptionError("Reform must be a number or an object.")
        return weights

    @staticmethod
    def _check_scenario(scenario: str) -> None:
        allowed = {"baseline", "adu", "missing_middle", "tod", "parking", "fees", "combined"}
        if scenario not in allowed:
            raise AssumptionError("Unknown scenario.")


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            # Quiet by default. Tests and local runs do not need access-line noise.
            return

        def _send(
            self,
            status: int,
            body: bytes,
            content_type: str,
            filename: str | None = None,
            cache_control: str | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", _CSP)
            self.send_header("Permissions-Policy", _PERMISSIONS)
            self.send_header("Cache-Control", cache_control or "no-store")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any, cache_control: str | None = None) -> None:
            self._send(
                status,
                json.dumps(payload).encode("utf-8"),
                "application/json; charset=utf-8",
                cache_control=cache_control,
            )

        def _read_json(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length", "0")
            length = parse_request_int(raw_length, 0, MAX_BODY, "Content-Length")
            if length < 0 or length > MAX_BODY:
                raise AssumptionError("Request body is too large")
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise AssumptionError("JSON body must be an object")
            return data

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/favicon.ico":
                self._send(204, b"", "image/x-icon")
                return
            if path in STATIC_FILES:
                name, content_type = STATIC_FILES[path]
                body = (STATIC_DIR / name).read_bytes()
                if path in HTML_PATHS:
                    body = _with_page_notes(body, path)
                self._send(200, body, content_type, cache_control=_static_cache(path, parse_qs(parsed.query)))
                return
            query = parse_qs(parsed.query)
            if path.startswith("/docs/"):
                body = read_doc(path)
                if body is None:
                    self._json(404, {"error": "Not found"})
                else:
                    self._send(200, body, "text/plain; charset=utf-8")
                return
            try:
                if path == "/api/health":
                    from src.version import build_info

                    self._json(200, {"ok": True, **build_info()})
                elif path == "/api/states":
                    self._json(200, app.states())
                elif path == "/api/assumptions":
                    state = query.get("state", ["PA"])[0]
                    self._json(200, app.assumption_catalog(state))
                elif path == "/api/export":
                    state = query.get("state", ["all"])[0]
                    fmt = query.get("format", ["csv"])[0]
                    body, mime, filename = app.export(state, fmt)
                    self._send(200, body, mime, filename)
                elif path == "/api/map":
                    raw_state = query.get("state")
                    if raw_state is not None:
                        app._check_state(raw_state[0])
                    self._json(200, app.map_points())
                elif path == "/api/case-study":
                    self._json(200, app.case_study())
                elif path == "/api/lab/results":
                    self._json(200, app.lab_results(query.get("state", ["PA"])[0]), cache_control=ASSET_CACHE)
                elif path == "/api/lab/geo":
                    self._json(200, app.lab_geo(query.get("state", ["PA"])[0]), cache_control=ASSET_CACHE)
                elif path == "/api/lab/assumptions":
                    self._json(200, app.lab_assumptions())
                elif path == "/api/lab/why":
                    self._json(
                        200,
                        app.lab_why(
                            {
                                "state": query.get("state", ["PA"])[0],
                                "county": query.get("county", ["Allegheny"])[0],
                                "scenario": query.get("scenario", ["adu"])[0],
                            }
                        ),
                    )
                elif path == "/api/lab/export":
                    county = query.get("county", [None])[0]
                    fmt = query.get("format", ["md"])[0]
                    body, mime, filename = app.lab_export(query.get("state", ["PA"])[0], fmt, county, None)
                    self._send(200, body, mime, filename)
                elif path == "/api/adu-compare":
                    self._json(200, app.adu_compare(query.get("state", ["PA"])[0]))
                else:
                    self._json(404, {"error": "Not found"})
            except AssumptionError as exc:
                self._json(400, {"error": public_error(str(exc))})
            except Exception:
                self._json(500, {"error": "Server error"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                payload = self._read_json()
                if parsed.path == "/api/simulate":
                    self._json(200, app.simulate(payload))
                elif parsed.path == "/api/case-study":
                    self._json(200, app.case_study(payload))
                elif parsed.path == "/api/sensitivity":
                    self._json(200, app.sensitivity(payload))
                elif parsed.path == "/api/crossval":
                    self._json(200, app.crossval(payload))
                elif parsed.path == "/api/lab/recompute":
                    self._json(200, app.lab_recompute(payload))
                elif parsed.path == "/api/lab/why":
                    self._json(200, app.lab_why(payload))
                elif parsed.path == "/api/export":
                    body, mime, filename = app.export(
                        str(payload.get("state", "PA")),
                        str(payload.get("format", "csv")),
                        payload.get("overrides"),
                        payload.get("reforms"),
                    )
                    self._send(200, body, mime, filename)
                elif parsed.path == "/api/lab/export":
                    body, mime, filename = app.lab_export(
                        str(payload.get("state", "PA")),
                        str(payload.get("format", "md")),
                        str(payload["county"]) if payload.get("county") else None,
                        payload.get("overrides"),
                        payload.get("reforms"),
                    )
                    self._send(200, body, mime, filename)
                else:
                    self._json(404, {"error": "Not found"})
            except AssumptionError as exc:
                self._json(400, {"error": public_error(str(exc))})
            except json.JSONDecodeError:
                self._json(400, {"error": "Body is not valid JSON"})
            except Exception:
                self._json(500, {"error": "Server error"})

    return Handler


ADU_NOTE_MARKER = b"<!-- ADU_FEE_NOTE -->"
ENGINE_GAP_MARKER = b"<!-- ENGINE_GAP -->"
BUILD_STAMP_MARKER = b"<!-- BUILD_STAMP -->"
_VERSIONED_ASSETS = (b"/tokens.css", b"/styles.css", b"/lab.css", b"/app.js", b"/lab.js")


def _static_cache(path: str, query: dict[str, list[str]]) -> str:
    """HTML stays fresh. Long caching is only for ?v= assets and, separately, Lab results."""
    if path in HTML_PATHS:
        return HTML_CACHE
    version = (query.get("v") or [""])[0]
    if version:
        return ASSET_CACHE
    return HTML_CACHE


def _version_asset_urls(body: bytes, version: str) -> bytes:
    if not version or version == "unknown":
        return body
    token = version.encode("utf-8")
    for asset in _VERSIONED_ASSETS:
        body = body.replace(asset + b'"', asset + b"?v=" + token + b'"')
        body = body.replace(asset + b"'", asset + b"?v=" + token + b"'")
    return body


def _with_page_notes(body: bytes, path: str) -> bytes:
    """Fill the fee note, the engine-gap callout, and the build stamp."""
    from src.adu_fee_note import engine_gap_html, note_html
    from src.version import build_info, stamp_html

    audience = "lab" if "lab" in path else "core"
    if ADU_NOTE_MARKER in body:
        body = body.replace(ADU_NOTE_MARKER, note_html(audience).encode("utf-8"), 1)
    if ENGINE_GAP_MARKER in body:
        gap = engine_gap_html(audience).encode("utf-8")
        body = body.replace(ENGINE_GAP_MARKER, gap)
    if BUILD_STAMP_MARKER in body:
        body = body.replace(BUILD_STAMP_MARKER, stamp_html().encode("utf-8"))
    return _version_asset_urls(body, str(build_info()["short_sha"]))


def serve(host: str = "127.0.0.1", port: int = 8080) -> None:
    app = App()
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"Stateframe is running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
