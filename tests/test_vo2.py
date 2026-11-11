import pytest

from mowl_to_garmin.vo2 import (
    Estimate,
    NoEstimate,
    acsm_vo2,
    estimate_vo2max,
    max_hr_from_age,
    read_samples,
)

from .conftest import INVALID_HR, INVALID_POWER, build_fit, ride_records

# Default synthetic ride: HR = 60 + 0.4 * P, so at max HR 180 the power is 300 W.
EXPECTED_75KG = acsm_vo2(300, 75)


def test_known_relation_gives_expected_estimate(ride_bytes):
    result = estimate_vo2max(ride_bytes, 75, 180)
    assert isinstance(result, Estimate)
    assert result.vo2max == pytest.approx(EXPECTED_75KG, abs=0.5)
    assert result.r2 == pytest.approx(1.0, abs=0.01)
    assert result.blocks >= 8


def test_acsm_equation():
    assert acsm_vo2(300, 75) == pytest.approx(10.8 * 4 + 7)


def test_heavier_rider_gets_lower_estimate(ride_bytes):
    light = estimate_vo2max(ride_bytes, 70, 180).vo2max
    heavy = estimate_vo2max(ride_bytes, 90, 180).vo2max
    assert heavy < light


def test_max_hr_from_age():
    assert max_hr_from_age(45) == 176
    assert max_hr_from_age(20) == 194


def test_invalid_samples_are_skipped():
    hr = lambda t: INVALID_HR if t % 10 == 0 else round(  # noqa: E731
        60 + 0.4 * (100 + 10 * (max(t - 45, 0) // 60)))
    raw = build_fit(ride_records(hr=hr))
    power, heart = read_samples(raw)
    assert heart[0] is None and heart[1] is not None
    result = estimate_vo2max(raw, 75, 180)
    assert result.vo2max == pytest.approx(EXPECTED_75KG, abs=0.5)


@pytest.mark.parametrize(
    "records, max_hr, reason",
    [
        (ride_records(power=lambda t: INVALID_POWER, hr=lambda t: 150), 180, "no power data"),
        (ride_records(hr=lambda t: INVALID_HR), 180, "no heart rate data"),
        (ride_records(seconds=4 * 60), 180, "steady blocks"),
        (ride_records(), 230, "heart rate too low"),
        (ride_records(power=lambda t: 200, hr=lambda t: 150), 180, "does not rise"),
        (ride_records(hr=lambda t: 150 + (t // 30 % 2) * 20 - (t // 90 % 2) * 15), 180,
         "fit too weak"),
    ],
)
def test_no_estimate(records, max_hr, reason):
    result = estimate_vo2max(build_fit(records), 75, max_hr)
    assert isinstance(result, NoEstimate)
    assert reason in result.reason
