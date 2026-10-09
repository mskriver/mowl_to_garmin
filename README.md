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

The tool has no dependencies outside the Python standard library and needs
Python 3.10 or newer. [uv](https://docs.astral.sh/uv/) is the recommended way
to install it:

```sh
# from a local checkout
uv tool install .

# or straight from git
uv tool install git+https://github.com/<you>/mowl-to-garmin

# or run it once without installing
uvx --from git+https://github.com/<you>/mowl-to-garmin mowl-to-garmin ride.fit
```

## Usage

```sh
mowl-to-garmin ride.fit                  # -> ride_garmin.fit
mowl-to-garmin folder/                   # every .fit in the folder
mowl-to-garmin a.fit b.fit c.fit
mowl-to-garmin ride.fit --product edge530
mowl-to-garmin ride.fit --product 3121   # any numeric Garmin product id
```

Converted files are written next to the originals with a `_garmin` suffix.
When you pass a folder, files that already end in `_garmin.fit` are skipped.
Upload the converted files to Garmin Connect (web: **Import Data**).

You can also run it as a module: `python -m mowl_to_garmin ...`.

### Device presets

| Name       | Product id |
|------------|-----------:|
| `edge830`  | 3122 (default) |
| `edge530`  | 3121 |
| `edge1030` | 2713 |

Any other product id from the FIT SDK can be passed as a number.

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

## Disclaimer

This project is not affiliated with or endorsed by Garmin. "Garmin", "Edge" and
"Garmin Connect" are trademarks of Garmin Ltd. or its subsidiaries. The tool
changes metadata in your activity files: keep your originals and use it at your
own risk.

## License

[MIT](LICENSE)
