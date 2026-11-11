"""Experimental VO2 Max estimate from power and heart rate of an indoor ride.

Method (submaximal heart rate / power extrapolation):

1. Take per-second power and heart rate from the ``record`` messages.
2. Use only the first part of the ride (``WINDOW_S``) to limit cardiac drift,
   averaged in ``BLOCK_S`` blocks, with heart rate lagged ``HR_LAG_S`` behind
   power because it reacts slowly to changes in effort.
3. Drop blocks where power jumped compared to the previous block (not steady).
4. Fit ``HR = a + b * power`` and extrapolate to the rider's max HR.
5. Convert that power to oxygen uptake with the ACSM leg-cycling equation:
   ``VO2 = 10.8 * watts / kg + 7`` (ml/kg/min).

This is an estimate for tracking trends, not Garmin's (Firstbeat) value.
"""

from dataclasses import dataclass

from .fit import iter_messages

MSG_RECORD = 20
FIELD_TIMESTAMP = 253
FIELD_HEART_RATE = 3
FIELD_POWER = 7
INVALID_UINT8 = 0xFF
INVALID_UINT16 = 0xFFFF

# Tunable constants
WINDOW_S = 12 * 60          # analyse only the first 12 minutes (20 min failed on intervals)
BLOCK_S = 30                # averaging block length
HR_LAG_S = 45               # heart rate trails power by this much
MIN_BLOCK_COVERAGE = 0.8    # share of valid samples a block needs
MAX_STEP_CHANGE = 0.15      # max relative power change vs. previous block
MIN_BLOCKS = 8
MIN_R2 = 0.7
MIN_PEAK_HR_FRACTION = 0.75  # peak HR in the window must reach this share of max HR
FLOOR_WINDOW_S = 5 * 60     # best-5-min power gives a lower bound


@dataclass(frozen=True)
class Estimate:
    vo2max: float
    r2: float
    blocks: int


@dataclass(frozen=True)
class NoEstimate:
    reason: str


def max_hr_from_age(age: int) -> int:
    """Tanaka et al. (2001): 208 - 0.7 * age."""
    return round(208 - 0.7 * age)


def acsm_vo2(watts: float, weight_kg: float) -> float:
    return 10.8 * watts / weight_kg + 7


def read_samples(raw: bytes):
    """Return per-second (power, heart_rate) lists; missing values are None."""
    points = {}
    for gnum, values in iter_messages(raw):
        if gnum != MSG_RECORD or FIELD_TIMESTAMP not in values:
            continue
        power = values.get(FIELD_POWER)
        hr = values.get(FIELD_HEART_RATE)
        points[values[FIELD_TIMESTAMP]] = (
            None if power in (None, INVALID_UINT16) else power,
            None if hr in (None, INVALID_UINT8, 0) else hr,
        )
    if not points:
        return [], []
    start = min(points)
    length = max(points) - start + 1
    power, hr = [None] * length, [None] * length
    for ts, (p, h) in points.items():
        power[ts - start] = p
        hr[ts - start] = h
    return power, hr


def _mean(values):
    valid = [v for v in values if v is not None]
    if len(valid) < MIN_BLOCK_COVERAGE * len(values):
        return None
    return sum(valid) / len(valid)


def _best_average(values, window):
    if len(values) < window:
        return None
    filled = [v or 0 for v in values]
    total = best = sum(filled[:window])
    for i in range(window, len(filled)):
        total += filled[i] - filled[i - window]
        best = max(best, total)
    return best / window


def _blocks(power, hr):
    """(power, hr) block averages that are steady, within the analysis window."""
    pairs = []
    previous = None
    end = min(WINDOW_S, len(power) - HR_LAG_S - BLOCK_S)
    for start in range(0, end + 1, BLOCK_S):
        p = _mean(power[start:start + BLOCK_S])
        h = _mean(hr[start + HR_LAG_S:start + HR_LAG_S + BLOCK_S])
        steady = bool(p and previous) and abs(p - previous) <= MAX_STEP_CHANGE * previous
        if steady and h is not None:
            pairs.append((p, h))
        previous = p
    return pairs


def _linear_fit(pairs):
    n = len(pairs)
    mx = sum(p for p, _ in pairs) / n
    my = sum(h for _, h in pairs) / n
    sxx = sum((p - mx) ** 2 for p, _ in pairs)
    syy = sum((h - my) ** 2 for _, h in pairs)
    sxy = sum((p - mx) * (h - my) for p, h in pairs)
    if sxx == 0 or syy == 0:
        return None
    slope = sxy / sxx
    return my - slope * mx, slope, sxy * sxy / (sxx * syy)


def estimate_vo2max(raw: bytes, weight_kg: float, max_hr: int):
    power, hr = read_samples(raw)
    if not any(p for p in power):
        return NoEstimate("no power data")
    if not any(hr):
        return NoEstimate("no heart rate data")

    pairs = _blocks(power, hr)
    if len(pairs) < MIN_BLOCKS:
        return NoEstimate(f"only {len(pairs)} steady blocks, need {MIN_BLOCKS}")
    if max(h for _, h in pairs) < MIN_PEAK_HR_FRACTION * max_hr:
        return NoEstimate("heart rate too low for a reliable extrapolation")

    fit = _linear_fit(pairs)
    if fit is None or fit[1] <= 0:
        return NoEstimate("heart rate does not rise with power")
    intercept, slope, r2 = fit
    if r2 < MIN_R2:
        return NoEstimate(f"heart rate/power fit too weak (R² {r2:.2f})")

    vo2max = acsm_vo2((max_hr - intercept) / slope, weight_kg)
    floor_power = _best_average(power, FLOOR_WINDOW_S)
    if floor_power is not None and vo2max < acsm_vo2(floor_power, weight_kg):
        return NoEstimate("estimate below what the best 5-min power implies")
    return Estimate(round(vo2max, 1), round(r2, 2), len(pairs))
