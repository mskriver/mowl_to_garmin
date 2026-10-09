import pytest
from typer.testing import CliRunner

from mowl_to_garmin import __version__
from mowl_to_garmin.cli import app
from mowl_to_garmin.fit import convert


@pytest.fixture
def run(monkeypatch):
    monkeypatch.delenv("MOWL_TO_GARMIN_PRODUCT", raising=False)
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
    for text in ("--product", "-p", "--version", "MOWL_TO_GARMIN_PRODUCT", "edge830"):
        assert text in result.output


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
