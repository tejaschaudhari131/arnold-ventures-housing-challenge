# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Stdlib HTTP server for the simulator.

Routes are a fixed map. Nothing the client sends is joined onto a filesystem
path. JSON bodies are size-capped. Assumption overrides are validated and
clamped by the assumption loader before they reach the equations.
"""

from __future__ import annotations

import json
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
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/lab": ("lab.html", "text/html; charset=utf-8"),
    "/lab.html": ("lab.html", "text/html; charset=utf-8"),
    "/lab.css": ("lab.css", "text/css; charset=utf-8"),
    "/lab.js": ("lab.js", "text/javascript; charset=utf-8"),
}
MAX_BODY = 64_000


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
        draws = int(payload.get("draws", 80))
        draws = max(20, min(draws, 400))
        return {
            "tornado": tornado(self.fixtures, self.assumptions, state, scenario),
            "monte_carlo": monte_carlo(self.fixtures, self.assumptions, state, scenario, draws=draws),
        }

    def crossval(self, payload: dict[str, Any]) -> dict[str, Any]:
        scope = str(payload.get("scope", "tier1"))
        draws = max(20, min(int(payload.get("draws", 40)), 200))
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
        )

    def lab_recompute(self, payload: dict[str, Any]) -> dict[str, Any]:
        from src.lab.explain import clamp_overrides, recompute

        county = payload.get("county")
        return recompute(
            str(payload.get("state", "PA")),
            clamp_overrides(payload.get("overrides")),
            str(county) if county else None,
        )

    def lab_export(self, state: str, fmt: str, county: str | None, overrides: dict[str, Any] | None) -> tuple[bytes, str, str]:
        from src.lab.explain import clamp_overrides, export_brief

        return export_brief(state, fmt, county, clamp_overrides(overrides) if overrides else None)

    def export(self, state: str, fmt: str) -> tuple[bytes, str, str]:
        if fmt not in {"csv", "json", "md"}:
            raise AssumptionError("format must be csv, json, or md")
        if state == "all":
            results = simulate_many(self.fixtures, self.assumptions)
            stem = "stateframe-all-states"
        else:
            results = simulate_many(self.fixtures, self.assumptions, [self._check_state(state)])
            stem = f"stateframe-{state}"
        if fmt == "csv":
            body, mime = to_csv(results), "text/csv; charset=utf-8"
        elif fmt == "md":
            body, mime = to_markdown(results), "text/markdown; charset=utf-8"
        else:
            body, mime = to_json(results), "application/json; charset=utf-8"
        return body.encode("utf-8"), mime, f"{stem}.{fmt if fmt != 'md' else 'md'}"

    def _check_state(self, state: str) -> str:
        code = state.strip().upper()
        if code not in self.fixtures["states"]:
            raise AssumptionError(f"Unknown state '{state}'")
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
                raise AssumptionError(f"Unknown reform '{key}'")
            if isinstance(value, bool):
                weights[key] = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                weights[key] = float(value)
            elif isinstance(value, dict):
                turned_on = bool(value.get("on", True))
                try:
                    weight = float(value.get("weight", 1.0))
                except (TypeError, ValueError) as exc:
                    raise AssumptionError(f"Reform '{key}' weight must be a number") from exc
                weights[key] = weight if turned_on else 0.0
            else:
                raise AssumptionError(f"Reform '{key}' must be a number or an object")
        return weights

    @staticmethod
    def _check_scenario(scenario: str) -> None:
        allowed = {"baseline", "adu", "missing_middle", "tod", "parking", "fees", "combined"}
        if scenario not in allowed:
            raise AssumptionError(f"Unknown scenario '{scenario}'")


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            # Quiet by default. Tests and local runs do not need access-line noise.
            return

        def _send(self, status: int, body: bytes, content_type: str, filename: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
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
                self._send(200, body, content_type)
                return
            query = parse_qs(parsed.query)
            try:
                if path == "/api/health":
                    self._json(200, {"ok": True})
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
                    self._json(200, app.map_points())
                elif path == "/api/case-study":
                    self._json(200, app.case_study())
                elif path == "/api/lab/results":
                    self._json(200, app.lab_results(query.get("state", ["PA"])[0]))
                elif path == "/api/lab/geo":
                    self._json(200, app.lab_geo(query.get("state", ["PA"])[0]))
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
                else:
                    self._json(404, {"error": "Not found"})
            except AssumptionError as exc:
                self._json(400, {"error": str(exc)})
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
                elif parsed.path == "/api/lab/export":
                    body, mime, filename = app.lab_export(
                        str(payload.get("state", "PA")),
                        str(payload.get("format", "md")),
                        str(payload["county"]) if payload.get("county") else None,
                        payload.get("overrides"),
                    )
                    self._send(200, body, mime, filename)
                else:
                    self._json(404, {"error": "Not found"})
            except AssumptionError as exc:
                self._json(400, {"error": str(exc)})
            except json.JSONDecodeError:
                self._json(400, {"error": "Body is not valid JSON"})
            except Exception:
                self._json(500, {"error": "Server error"})

    return Handler


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
