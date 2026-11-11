# mowl-to-garmin

Make `.fit` activity files look like they were recorded on a Garmin device, so
Garmin Connect calculates **Training Effect**, **Training Load** and related
metrics for them.

Garmin Connect only runs its physiological analysis on activities that were
recorded by a Garmin device. If you record on something else, such as an indoor
trainer app, a bike computer from another brand or a phone, the upload works
but those metrics are missing. `mowl-to-garmin` rewrites the device identity in
the file. Your actual data is not changed.

## Installation

The tool needs Python 3.10 or newer. [uv](https://docs.astral.sh/uv/) is the
recommended way to install it:

```sh
# install a specific release (v0.1.1)
uv tool install git+https://github.com/mskriver/mowl_to_garmin@v0.1.1

# or the latest development version (HEAD of main), which may be unreleased
uv tool install git+https://github.com/mskriver/mowl_to_garmin@main

# or from a local checkout
uv tool install .

# or run it once without installing
uvx --from git+https://github.com/mskriver/mowl_to_garmin@v0.1.1 mowl-to-garmin ride.fit
```

Check the installation with `mowl-to-garmin --version`.

### Upgrading

Rerun the install command with `--force` and the release you want, or with
`@main` to pick up new commits:

```sh
# move to a newer release, for example v0.2.0
uv tool install --force git+https://github.com/mskriver/mowl_to_garmin@v0.2.0

# or update to the latest main
uv tool install --force git+https://github.com/mskriver/mowl_to_garmin@main
```

An install pinned to a tag stays on that tag, so `uv tool upgrade` will not move
it to a newer release.

### Uninstalling

```sh
uv tool uninstall mowl-to-garmin
```

## Usage

```sh
mowl-to-garmin ride.fit                  # -> ride_garmin.fit
mowl-to-garmin folder/                   # every .fit in the folder
mowl-to-garmin a.fit b.fit c.fit
mowl-to-garmin ride.fit --product edge530
mowl-to-garmin ride.fit -p 3121          # any numeric Garmin product id
```

Converted files are written next to the originals with a `_garmin` suffix.
When you pass a folder, files that already end in `_garmin.fit` are skipped.
Upload the converted files to Garmin Connect (web: **Import Data**).

```
🔄 Converting 3 files to Garmin edge830 (product 3122)...

❌ broken.fit: not a FIT file
✅ ride1.fit → ride1_garmin.fit
✅ ride2.fit → ride2_garmin.fit

======================================================================
Conversion Summary
----------------------------------------------------------------------
3 files, 2 converted, 1 failed
======================================================================

Total runtime: 0.01s

❌ 1 out of 3 files failed to convert
```

The exit code is 0 when every file converted and 1 otherwise.

### Options

| Option | Environment variable | Description |
|--------|----------------------|-------------|
| `-p`, `--product` | `MOWL_TO_GARMIN_PRODUCT` | Device preset name or numeric product id (default `edge830`) |
| `--vo2` | | **Experimental.** Print a VO2 Max estimate per ride (off by default, see below) |
| `--weight` | `MOWL_TO_GARMIN_WEIGHT` | Body weight in kg, needed for `--vo2` |
| `--max-hr` | `MOWL_TO_GARMIN_MAX_HR` | Max heart rate in bpm, needed for `--vo2` |
| `--age` | `MOWL_TO_GARMIN_AGE` | Age, used to estimate max heart rate when `--max-hr` is not given |
| `--version` | | Print the version and exit |
| `--help` | | Show the help and exit |

Set `NO_COLOR=1` to turn off colored output.

You can also run it as a module: `python -m mowl_to_garmin ...`.

### Device presets

| Name       | Product id |
|------------|-----------:|
| `edge830`  | 3122 (default) |
| `edge530`  | 3121 |
| `edge1030` | 2713 |

Any other product id from the FIT SDK can be passed as a number.

### VO2 Max estimate (experimental)

> [!WARNING]
> `--vo2` is an **experimental** feature. The estimate has not yet been
> validated against Garmin's own VO2 Max values. The method, its thresholds and
> the output format may change in any release, and the option may be removed.
> Use it to follow your own trend, not as a measurement.

```sh
mowl-to-garmin ride.fit --vo2 --weight 80 --max-hr 182
# ✅ ride.fit → ride_garmin.fit · VO2 Max est. 56.8 (R² 0.78, 18 blocks)
```

With `--vo2` the tool prints an estimate of your cycling VO2 Max (ml/kg/min)
for each ride. The converted file is **not** changed, and Garmin Connect will
not show this value. It is meant for watching your own trend across sessions.

How it works: the tool fits heart rate against power over the steady parts of
the first 12 minutes of the ride, extrapolates to your max heart rate, and
converts that power to oxygen uptake with the ACSM cycling equation
(`10.8 × watts / kg + 7`). The ride needs power and heart rate. If the data
is too short, too uneven or too easy, the tool prints `not enough data` and
the reason instead of a number.

**Finding your max heart rate:** use the value under heart rate zones in your
Garmin Connect user settings, or the user profile on your watch. Many watches
update it automatically from hard efforts. If you don't know it, pass `--age`
instead: the tool then uses `208 − 0.7 × age`, which can be off by about 10 bpm
and moves the estimate by about 5 ml/kg/min. If `--weight` or a max heart rate
is missing, `--vo2` prints a warning and only converts the files.

Set the values once with the environment variables listed above, so you don't
have to repeat them.

## Limitations

Some Garmin Connect metrics can't be produced by changing a file:

- **VO2 Max** is calculated on the Garmin device and stored in the files it
  records. Garmin Connect doesn't calculate it for uploaded files, and most
  devices don't produce one for indoor rides anyway. Converted rides therefore
  don't update your VO2 Max chart.
- **Intensity Minutes, Vigorous Minutes and Vigorous Days** (used for Fitness
  Age) come from the all-day heart rate tracking of a Garmin watch, not from
  uploaded activities. Wear your Garmin watch during the session and it counts
  these minutes itself, without starting an activity on it.

## How it works

A FIT file names the recording device in two places: the `file_id` message and
the "creator" `device_info` message (`device_index` 0). The tool:

1. sets `manufacturer` to Garmin (1) and `product` to the chosen device in both places,
2. adds the `manufacturer`/`product` fields to `file_id` if the file has none,
3. recomputes the header and file CRCs.

Everything else, including heart rate, power, cadence, laps, timestamps, other
sensors' `device_info` and developer fields, is copied byte for byte.

## Development

```sh
uv sync                 # create .venv with dev dependencies
uv run pytest           # run the tests
uv run ruff check .     # lint
uv build                # build sdist + wheel into dist/
```

## Contributing

Bug reports and ideas are welcome on the
[issue tracker](https://github.com/mskriver/mowl-to-garmin/issues).

For a bug, please include:

- the output of `mowl-to-garmin --version` and your Python version,
- the app or device that recorded the file,
- the full output of the failing command,
- what Garmin Connect did with the converted file, if it got that far.

A sample `.fit` file helps a lot, but note that these files contain GPS tracks
and health data. Only attach one you are comfortable making public.

Pull requests are welcome too. Please run `uv run pytest` and
`uv run ruff check .` first, and add a test for any change to the conversion
logic.

## Disclaimer

This project is not affiliated with or endorsed by Garmin. "Garmin", "Edge" and
"Garmin Connect" are trademarks of Garmin Ltd. or its subsidiaries. The tool
changes metadata in your activity files: keep your originals and use it at your
own risk.

## License

[MIT](LICENSE)
