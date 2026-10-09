import pytest

from mowl_to_garmin import __version__
from mowl_to_garmin.cli import main
from mowl_to_garmin.fit import convert


def test_converts_single_file(tmp_path, fit_bytes):
    src = tmp_path / "ride.fit"
    src.write_bytes(fit_bytes)
    assert main([str(src)]) == 0
    assert (tmp_path / "ride_garmin.fit").exists()


def test_folder_skips_already_converted(tmp_path, fit_bytes, capsys):
    (tmp_path / "a.fit").write_bytes(fit_bytes)
    (tmp_path / "b_garmin.fit").write_bytes(fit_bytes)
    assert main([str(tmp_path), "--product", "edge1030"]) == 0
    out = capsys.readouterr().out
    assert "1/1 converted" in out
    assert not (tmp_path / "b_garmin_garmin.fit").exists()


def test_failure_returns_nonzero(tmp_path):
    bad = tmp_path / "bad.fit"
    bad.write_bytes(b"\x0e" + b"\x00" * 20)
    assert main([str(bad)]) == 1


def test_empty_folder(tmp_path):
    assert main([str(tmp_path)]) == 1


def test_invalid_product_is_clean_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--product", "foo"])
    assert exc.value.code == 2
    assert "not a product id" in capsys.readouterr().err


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out


def test_original_file_is_left_untouched(tmp_path, fit_bytes):
    src = tmp_path / "ride.fit"
    src.write_bytes(fit_bytes)
    main([str(src)])
    assert src.read_bytes() == fit_bytes


def test_output_matches_convert(tmp_path, fit_bytes):
    src = tmp_path / "ride.fit"
    src.write_bytes(fit_bytes)
    main([str(src), "--product", "3121"])
    assert (tmp_path / "ride_garmin.fit").read_bytes() == convert(fit_bytes, 3121)


def test_product_name_is_case_insensitive(tmp_path, fit_bytes):
    src = tmp_path / "ride.fit"
    src.write_bytes(fit_bytes)
    assert main([str(src), "--product", "EDGE530"]) == 0
    assert (tmp_path / "ride_garmin.fit").read_bytes() == convert(fit_bytes, 3121)


def test_mixed_results_report_partial_failure(tmp_path, fit_bytes, capsys):
    (tmp_path / "good.fit").write_bytes(fit_bytes)
    (tmp_path / "bad.fit").write_bytes(b"not a fit file at all")
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "OK    good.fit -> good_garmin.fit" in out
    assert "FAIL  bad.fit" in out
    assert "1/2 converted" in out


def test_missing_file_fails(tmp_path, capsys):
    assert main([str(tmp_path / "nope.fit")]) == 1
    assert "FAIL  nope.fit" in capsys.readouterr().out


def test_multiple_paths(tmp_path, fit_bytes):
    for name in ("a.fit", "b.fit"):
        (tmp_path / name).write_bytes(fit_bytes)
    assert main([str(tmp_path / "a.fit"), str(tmp_path / "b.fit")]) == 0
    assert (tmp_path / "a_garmin.fit").exists() and (tmp_path / "b_garmin.fit").exists()


def test_no_arguments_is_usage_error():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
