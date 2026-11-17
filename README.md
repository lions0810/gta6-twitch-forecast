# GTA VI Twitch CCU forecast — pooled release-day shape

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/lions0810/gta6-twitch-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/lions0810/gta6-twitch-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

An entry to make.fun's [GTA VI Twitch forecast bounty](https://make.fun/bounty/gta6-twitch-ccu-forecast-01).

Entry for make.fun's `gta6-twitch-ccu-forecast-01`: forecast a launch day's
Twitch category viewers for hours 2–24 of the UTC release day, at the five
quantiles 0.05 / 0.25 / 0.5 / 0.75 / 0.95, from hour 1's print and the case's
comparable past launches. The final case is Grand Theft Auto VI's release
day, 2026-11-19, scored against real Twitch data with pinball loss.

## The model

Each hour is forecast as **hour 1's level × a pooled release-day shape**:

    q_tau(h) = p1 * exp( weighted_quantile_tau( { log( v_c(h) / v_c(1) ) }, w_c ) )

For every comparable with a complete release day (all 24 hourly buckets,
hour 1 above zero), its day is normalized by its own hour 1. The forecast
ratio at each hour and level is a weighted quantile of the pool's log-ratios
(linear interpolation on cumulative-weight edges), with weights

    w_c = exp( -|log p1 − log h1_c| / 0.75 )  ·  exp( −(takeoff_c − 1) / 6 )

- the **scale kernel** pools launches of similar size (hour-1 viewers within
  a factor of ~e^0.75 weigh e⁻¹ less);
- the **takeoff kernel** pools launches whose day ignites at a similar time:
  `takeoff_c` is the first hour a comparable reaches 25% of its release-day
  peak. This is the dominant structure in the data — a rolling-midnight
  launch is already live at hour 1 (ratios dip, then rise to ~1.5× by US
  prime time), while a 14:00Z global unlock sits near zero for hours and
  then jumps 100×+. Mixing the two families unweighted poisons the upper
  quantiles; weighting by takeoff time (and scale) separates them smoothly.

Quantiles are taken directly from the cross-launch distribution of
normalized values — no parametric band is fitted.

## Validation (leave-one-out over the comparables)

Each of the 37 usable comparables in the practice pool was treated in turn
as a pseudo-case (its hour 1 known, the other 36 as its pool), forecasting
hours 2–24 and scoring mean pinball loss at the five levels against its
actual curve:

| model | overall | q05 | q25 | q50 | q75 | q95 |
|---|---|---|---|---|---|---|
| starter persistence (baseline) | 35,870 | 6,721 | 28,133 | 44,451 | 54,417 | 45,630 |
| pooled shape, unweighted | 291,629 | 5,647 | 27,492 | 61,895 | 159,833 | 1,203,280 |
| **this entry (scale + takeoff kernels)** | **25,671** | **5,398** | **21,192** | **36,202** | **41,702** | **23,859** |

The shipped model beats the baseline by **28% overall and at every level**
(q95 by 48%). On the subset of pseudo-cases most like the final (rolling
unlock, hour 1 ≥ 100k) it scores 30,178 against the baseline's 45,772.

Design choices were iterated only against this benchmark. Tested and
rejected because they scored worse out of sample: unweighted pooling;
hard pool cutoffs by takeoff hour (worse than the soft kernel); text-class
pool matching from the notes/unlock fields (no gain over the kernels);
blending toward persistence (α = 0.10 → 26,498); a pre-launch-history floor
(→ 25,969 at ×1, 27,911 at ×2); shrinking the upper quantiles toward the
median. The shipped design is the simplest variant that was clearly best.

## Safety

An invalid case forfeits all prizes, so the program is built to always emit
a valid file: the model path is wrapped per case — any exception, an
unusable pool, or a row that fails the output contract falls back to the
starter's persistence forecast (kept verbatim), and a case even persistence
cannot read gets a minimal valid file. Model rows are rounded half-up to 2
decimals, clamped into (0, 1e9], and forced non-decreasing before writing.

## Running

Standard library only (Python 3.13), no network, deterministic
(PYTHONHASHSEED=0; no randomness, no clock, sorted iteration):

    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py

`main.py` is the program the grader runs (`python3 -P -s /bot/main.py`);
`model.py` beside it holds the shape model. Data: SullyGnome hourly Twitch
category averages, as provided in the case files (see the kit's NOTICE.txt).
