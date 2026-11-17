"""gta6-twitch-ccu-forecast-01 entry: pooled release-day shape model.

Forecasts each hour of release day as hour 1's print times a pooled
release-day shape built from the case's comparables (see model.py and
README.md). The starter's persistence forecast is kept verbatim as the
fallback: any failure in the model path -- an exception, an unusable
comparables pool, an invalid row -- falls back to persistence for that case,
and a case that even persistence cannot read gets a minimal valid file.
An invalid case forfeits every prize, so no case is ever left unwritten or
malformed.

How the grader runs it: `python3 -P -s /bot/main.py` (PYTHONHASHSEED=0) in
python:3.13-slim, standard library only: no network, no pip packages. -P
keeps this file's directory OFF sys.path, so the sys.path line below puts it
back first and `import model` finds the model.py shipped beside this file;
-s drops user site-packages.

Input/output contract (from the starter): read every <id>.in in the input
directory (JSON case, schema makefun/twitch-ccu-case/v1); write <id>.out to
the output directory: {"hours": [{"hour": 2, "q": [q05, q25, q50, q75,
q95]}, ...]}, exactly 23 rows for hours 2..24, each q five finite numbers
above 0 and at most 1e9, non-decreasing; at most 65,536 bytes. Outside the
grader's container, MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR stand in for
/input and /output.
"""

import json
import math
import os
import sys
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so `import model` finds a model.py shipped beside this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import model

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.645, -0.674, 0, 0.674, 1.645]
# The spread of an hour's move, in natural-log units per square-root hour.
SIGMA = 0.15


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100 rounds it.

    A whole number comes back as an int, so json.dumps writes 1240 where JavaScript writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def hour_quantiles(p1: float, h: int) -> list[float | int]:
    """The persistence forecast of hour h: the five quantiles around hour 1's print."""
    return [round2(p1 * math.exp(z * SIGMA * math.sqrt(h - 1))) for z in Z]


def persistence_case(case: dict, name: str) -> dict:
    """The starter's forecast, unchanged: persistence around hour 1's print."""
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])
    return {"hours": [{"hour": row["hour"], "q": hour_quantiles(p1, row["hour"])} for row in case["forecast"]]}


def _clean_row(values: list[float]) -> list[float | int] | None:
    """Round a model row and force the output contract, or return None.

    Rounding to 2 decimals, clamping into (0, 1e9], and a cumulative maximum
    keep the five quantiles finite, positive and non-decreasing.
    """
    if len(values) != len(LEVELS):
        return None
    out: list[float | int] = []
    prev = 0.0
    for v in values:
        if not math.isfinite(v):
            return None
        q = round2(min(max(v, 0.01), 1e9))
        q = max(q, prev)
        if q <= 0 or q > 1e9:
            return None
        out.append(q)
        prev = float(q)
    return out


def model_case(case: dict) -> dict:
    """The pooled-shape forecast for one case. Raises on any problem."""
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError("no hour-1 print")
    p1 = max(1, float(first["viewers"]))
    hours = [row["hour"] for row in case["forecast"]]
    raw = model.forecast(case, p1, hours)
    rows = []
    for h in hours:
        cleaned = _clean_row(raw[h])
        if cleaned is None:
            raise ValueError(f"invalid model row for hour {h}")
        rows.append({"hour": h, "q": cleaned})
    return {"hours": rows}


def valid_output(obj: dict) -> bool:
    """The full output contract, checked before anything is written."""
    try:
        rows = obj["hours"]
        if len(rows) != 23:
            return False
        seen = set()
        for row in rows:
            if set(row.keys()) != {"hour", "q"}:
                return False
            h = row["hour"]
            if h in seen or not (2 <= h <= 24):
                return False
            seen.add(h)
            q = row["q"]
            if len(q) != 5:
                return False
            prev = 0.0
            for v in q:
                if not isinstance(v, (int, float)) or not math.isfinite(v):
                    return False
                if v <= 0 or v > 1e9 or v < prev:
                    return False
                prev = v
        return seen == set(range(2, 25))
    except Exception:
        return False


def forecast_case(case: dict, name: str) -> dict:
    """Model first, persistence on any failure, minimal valid file last."""
    try:
        out = model_case(case)
        if valid_output(out):
            return out
    except Exception:
        pass
    try:
        out = persistence_case(case, name)
        if valid_output(out):
            return out
    except Exception:
        pass
    # Last resort: a flat, valid file for hours 2..24 whatever the case held.
    return {"hours": [{"hour": h, "q": [1, 1, 1, 1, 1]} for h in range(2, 25)]}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
            forecast = forecast_case(case, path.name)
        except Exception:
            forecast = {"hours": [{"hour": h, "q": [1, 1, 1, 1, 1]} for h in range(2, 25)]}
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
