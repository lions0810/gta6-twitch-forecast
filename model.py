"""Release-day shape model for gta6-twitch-ccu-forecast-01.

Forecast: each hour's viewers = hour 1's print x a pooled release-day shape.

The shape comes from the case's own comparables. For every comparable with a
complete release day (all 24 hourly buckets present, hour 1 above zero), take
its hourly viewers normalized by its own hour 1, r_c(h) = v_c(h) / v_c(1).
For each forecast hour and each scored level, the forecast ratio is a weighted
quantile of {log r_c(h)} across the pool, exponentiated back:

    q_tau(h) = p1 * exp(weighted_quantile_tau({log r_c(h)}, w_c))

with per-comparable weights

    w_c = exp(-|log p1 - log h1_c| / 0.75) * exp(-(tau_c - 1) / 6),

where h1_c is the comparable's hour-1 viewers and tau_c its "takeoff hour"
(the first hour reaching 25% of its release-day peak). The first factor pools
launches of similar scale; the second pools launches whose day ignites at a
similar time (a rolling-midnight launch is already live at hour 1, a 14:00Z
global unlock is not, and their normalized shapes differ by orders of
magnitude). Design choices were selected by leave-one-out over the
comparables (each comparable in turn as a pseudo-case), scoring mean pinball
loss at the five levels; see README.md for the numbers. Blends toward the
persistence baseline and a pre-launch-history floor were tested the same way
and rejected: both scored worse out of sample.

Standard library only, no network, deterministic: no randomness, no wall
clock, iteration only over the case's own lists in their given order and over
explicitly sorted values.
"""

import math
from datetime import datetime, timedelta

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]

# Kernel bandwidth for scale similarity, in natural-log units of hour-1 viewers.
SCALE_BANDWIDTH = 0.75
# Decay scale, in hours, for the takeoff-time kernel.
TAKEOFF_SCALE = 6.0
# A comparable's takeoff hour: first hour at or above this share of its peak.
TAKEOFF_SHARE = 0.25


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _release_day(comp: dict) -> list[float] | None:
    """The comparable's release-day hourly viewers, hours 1..24, or None.

    Points are bucketed by hour offset from the comparable's day_start and
    averaged within a bucket (an hour's figure is the mean of its points).
    A comparable counts only with all 24 buckets present and hour 1 > 0.
    """
    try:
        start = _parse(comp["day_start"])
        buckets: dict[int, list[float]] = {}
        for pt in comp["hourly"]:
            t = _parse(pt["from"])
            if start <= t < start + timedelta(hours=24):
                hour = int((t - start).total_seconds() // 3600) + 1
                buckets.setdefault(hour, []).append(float(pt["viewers"]))
        if len(buckets) != 24:
            return None
        day = [sum(buckets[h]) / len(buckets[h]) for h in range(1, 25)]
    except Exception:
        return None
    if day[0] <= 0 or any(v < 0 for v in day):
        return None
    return day


def _takeoff(day: list[float]) -> int:
    peak = max(day)
    for i, v in enumerate(day):
        if v >= TAKEOFF_SHARE * peak:
            return i + 1
    return 24


def _wquantile(pairs: list[tuple[float, float]], tau: float) -> float:
    """Weighted quantile by linear interpolation on cumulative-weight edges.

    Each point's mass ends at its cumulative edge; for equal weights this
    tracks the type-7 quantile closely. Input is sorted here, by value then
    weight, so the result does not depend on pool order.
    """
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    if total <= 0:
        return ordered[len(ordered) // 2][0]
    target = tau * total
    cum = 0.0
    prev_v, prev_cum = ordered[0][0], 0.0
    for v, w in ordered:
        cum += w
        if cum >= target:
            if cum == prev_cum:
                return v
            return prev_v + (v - prev_v) * (target - prev_cum) / (cum - prev_cum)
        prev_v, prev_cum = v, cum
    return ordered[-1][0]


def forecast(case: dict, p1: float, hours: list[int]) -> dict[int, list[float]]:
    """Model quantiles per forecast hour: {hour: [q05, q25, q50, q75, q95]}.

    Raises on any unusable input; the caller falls back to persistence.
    """
    game_name = str(case.get("game", {}).get("name", "")).strip().lower()
    pool: list[tuple[list[float], float]] = []  # (release day, weight)
    for comp in case.get("comparables") or []:
        if str(comp.get("name", "")).strip().lower() == game_name and game_name:
            continue  # never pool the target launch itself
        day = _release_day(comp)
        if day is None:
            continue
        h1_c = day[0]
        w = math.exp(-abs(math.log(p1) - math.log(h1_c)) / SCALE_BANDWIDTH)
        w *= math.exp(-(_takeoff(day) - 1) / TAKEOFF_SCALE)
        if w > 0 and math.isfinite(w):
            pool.append((day, w))
    if not pool:
        raise ValueError("no usable comparables")
    out: dict[int, list[float]] = {}
    for h in hours:
        pairs_by_level: list[list[tuple[float, float]]] = [[] for _ in LEVELS]
        for day, w in pool:
            log_r = math.log(day[h - 1] / day[0])
            for i in range(len(LEVELS)):
                pairs_by_level[i].append((log_r, w))
        row = []
        for i, tau in enumerate(LEVELS):
            q = p1 * math.exp(_wquantile(pairs_by_level[i], tau))
            if not math.isfinite(q) or q <= 0:
                raise ValueError("non-finite forecast")
            row.append(q)
        out[h] = row
    return out
