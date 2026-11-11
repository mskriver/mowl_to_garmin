import re

import pytest
from typer.testing import CliRunner

from mowl_to_garmin import __version__
from mowl_to_garmin.cli import app
from mowl_to_garmin.fit import convert

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def run(monkeypatch):
    for var in ("PRODUCT", "WEIGHT", "MAX_HR", "AGE"):
        monkeypatch.delenv(f"MOWL_TO_GARMIN_{var}", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "200")
    runner = CliRunner()

    def _run(*args, **kwargs):
        return runner.invoke(app, [str(a) for a in args], **kwargs)

    return _run


@pytest.fixture
def ride(tmp_path, fit_bytes):
    src = tmp_path / "ride.fit"
    src.write_bytes(fit_bytes)
    return src


def test_converts_single_file(run, ride):
    result = run(ride)
    assert result.exit_code == 0
    assert ride.with_name("ride_garmin.fit").exists()
    assert "✅ ride.fit → ride_garmin.fit" in result.output
    assert "✅ All files converted: 1 out of 1" in result.output


def test_folder_skips_already_converted(run, tmp_path, fit_bytes):
    (tmp_path / "a.fit").write_bytes(fit_bytes)
    (tmp_path / "b_garmin.fit").write_bytes(fit_bytes)
    result = run(tmp_path, "--product", "edge1030")
    assert result.exit_code == 0
    assert "1 file, 1 converted, 0 failed" in result.output
    assert not (tmp_path / "b_garmin_garmin.fit").exists()


def test_failure_returns_nonzero(run, tmp_path):
    bad = tmp_path / "bad.fit"
    bad.write_bytes(b"\x0e" + b"\x00" * 20)
    result = run(bad)
    assert result.exit_code == 1
    assert "❌ bad.fit: not a FIT file" in result.output


def test_empty_folder(run, tmp_path):
    result = run(tmp_path)
    assert result.exit_code == 1
    assert "No .fit files found." in result.output


def test_invalid_product_is_clean_error(run, tmp_path):
    result = run(tmp_path, "--product", "foo")
    assert result.exit_code == 2
    assert "not a product id" in result.output


def test_version(run):
    result = run("--version")
    assert result.exit_code == 0
    assert result.output.strip() == f"mowl-to-garmin, version {__version__}"


def test_help_lists_options(run):
    result = run("--help")
    assert result.exit_code == 0
    output = ANSI_ESCAPE.sub("", result.output)
    for text in ("--product", "-p", "--version", "MOWL_TO_GARMIN_PRODUCT", "edge830",
                 "--vo2", "--weight", "--max-hr", "--age", "MOWL_TO_GARMIN_MAX_HR"):
        assert text in output


def test_original_file_is_left_untouched(run, ride, fit_bytes):
    run(ride)
    assert ride.read_bytes() == fit_bytes


def test_output_matches_convert(run, ride, fit_bytes):
    run(ride, "--product", "3121")
    assert ride.with_name("ride_garmin.fit").read_bytes() == convert(fit_bytes, 3121)


def test_short_product_flag(run, ride, fit_bytes):
    assert run(ride, "-p", "edge530").exit_code == 0
    assert ride.with_name("ride_garmin.fit").read_bytes() == convert(fit_bytes, 3121)


def test_product_name_is_case_insensitive(run, ride, fit_bytes):
    assert run(ride, "--product", "EDGE530").exit_code == 0
    assert ride.with_name("ride_garmin.fit").read_bytes() == convert(fit_bytes, 3121)


def test_product_from_environment(run, ride, fit_bytes):
    result = run(ride, env={"MOWL_TO_GARMIN_PRODUCT": "edge1030"})
    assert result.exit_code == 0
    assert "Garmin edge1030 (product 2713)" in result.output
    assert ride.with_name("ride_garmin.fit").read_bytes() == convert(fit_bytes, 2713)


def test_header_names_the_target_device(run, ride):
    assert "🔄 Converting 1 file to Garmin edge830 (product 3122)..." in run(ride).output
    assert "to Garmin product 9999..." in run(ride, "-p", "9999").output


def test_mixed_results_report_partial_failure(run, tmp_path, fit_bytes):
    (tmp_path / "good.fit").write_bytes(fit_bytes)
    (tmp_path / "bad.fit").write_bytes(b"not a fit file at all")
    result = run(tmp_path)
    assert result.exit_code == 1
    assert "✅ good.fit → good_garmin.fit" in result.output
    assert "❌ bad.fit" in result.output
    assert "2 files, 1 converted, 1 failed" in result.output
    assert "❌ 1 out of 2 files failed to convert" in result.output


def test_summary_block(run, ride):
    lines = run(ride).output.splitlines()
    start = lines.index("Conversion Summary")
    assert lines[start - 1] == "=" * 70
    assert lines[start + 1] == "-" * 70
    assert lines[start + 2] == "1 file, 1 converted, 0 failed"
    assert lines[start + 3] == "=" * 70
    assert any(line.startswith("Total runtime: ") for line in lines)


def test_no_ansi_codes_with_no_color(run, tmp_path, fit_bytes):
    (tmp_path / "good.fit").write_bytes(fit_bytes)
    (tmp_path / "bad.fit").write_bytes(b"nope")
    assert "\x1b[" not in run(tmp_path, color=True).output


def test_colors_when_enabled(run, tmp_path, fit_bytes, monkeypatch):
    monkeypatch.delenv("NO_COLOR")
    (tmp_path / "good.fit").write_bytes(fit_bytes)
    (tmp_path / "bad.fit").write_bytes(b"nope")
    assert "\x1b[" in run(tmp_path, color=True).output


def test_missing_file_fails(run, tmp_path):
    result = run(tmp_path / "nope.fit")
    assert result.exit_code == 1
    assert "❌ nope.fit" in result.output


def test_multiple_paths(run, tmp_path, fit_bytes):
    for name in ("a.fit", "b.fit"):
        (tmp_path / name).write_bytes(fit_bytes)
    assert run(tmp_path / "a.fit", tmp_path / "b.fit").exit_code == 0
    assert (tmp_path / "a_garmin.fit").exists() and (tmp_path / "b_garmin.fit").exists()


def test_no_arguments_is_usage_error(run):
    assert run().exit_code == 2


@pytest.fixture
def power_ride(tmp_path, ride_bytes):
    src = tmp_path / "ride.fit"
    src.write_bytes(ride_bytes)
    return src


def test_vo2_estimate_is_printed(run, power_ride, ride_bytes):
    result = run(power_ride, "--vo2", "--weight", "75", "--max-hr", "180")
    assert result.exit_code == 0
    assert "✅ ride.fit → ride_garmin.fit · VO2 Max est. 50.2 (R² 1.00," in result.output
    # the output file is the same as without --vo2
    assert power_ride.with_name("ride_garmin.fit").read_bytes() == convert(ride_bytes, 3122)


def test_vo2_is_off_by_default(run, power_ride):
    result = run(power_ride, "--weight", "75", "--max-hr", "180")
    assert "VO2" not in result.output


@pytest.mark.parametrize(
    "args, missing",
    [
        ((), "weight, max heart rate"),
        (("--max-hr", "180"), "weight"),
        (("--weight", "75"), "max heart rate"),
    ],
)
def test_vo2_missing_inputs_warns_but_converts(run, power_ride, args, missing):
    result = run(power_ride, "--vo2", *args)
    assert result.exit_code == 0
    assert f"⚠️  --vo2 needs --weight and --max-hr or --age (missing: {missing})" in result.output
    assert "✅ ride.fit → ride_garmin.fit\n" in result.output
    assert "VO2 Max est." not in result.output


def test_vo2_age_fallback(run, power_ride):
    result = run(power_ride, "--vo2", "--weight", "75", "--age", "40")
    assert result.exit_code == 0
    assert "Max heart rate estimated from age as 180 bpm" in result.output
    assert "VO2 Max est. 50.2" in result.output


def test_vo2_max_hr_overrides_age(run, power_ride):
    result = run(power_ride, "--vo2", "--weight", "75", "--max-hr", "180", "--age", "70")
    assert "estimated from age" not in result.output
    assert "VO2 Max est. 50.2" in result.output


def test_vo2_inputs_from_environment(run, power_ride):
    env = {"MOWL_TO_GARMIN_WEIGHT": "75", "MOWL_TO_GARMIN_MAX_HR": "180"}
    result = run(power_ride, "--vo2", env=env)
    assert "VO2 Max est. 50.2" in result.output


def test_vo2_not_enough_data(run, ride):
    result = run(ride, "--vo2", "--weight", "75", "--max-hr", "180")
    assert result.exit_code == 0
    assert "· VO2 Max: not enough data (no power data)" in result.output


def test_vo2_out_of_range_input_is_usage_error(run, power_ride):
    assert run(power_ride, "--vo2", "--weight", "5", "--max-hr", "180").exit_code == 2
