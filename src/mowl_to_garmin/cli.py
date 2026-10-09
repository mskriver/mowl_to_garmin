"""
mowl-to-garmin - make .fit files look like they were recorded on a Garmin
device, so Garmin Connect calculates Training Effect / Training Load for them.

Only the device fields are changed (manufacturer + product in the file_id
message, and in the "creator" device_info message). Everything else - heart
rate, power, cadence, laps, timestamps - is copied byte for byte.

Usage:
    mowl-to-garmin ride.fit              -> ride_garmin.fit
    mowl-to-garmin folder/               -> every .fit in folder
    mowl-to-garmin a.fit b.fit c.fit
    mowl-to-garmin ride.fit --product 3121   (pick another device)
"""

import argparse
import sys
from pathlib import Path

from . import __version__
from .fit import DEFAULT_PRODUCT, PRODUCTS, convert


def parse_product(value):
    product = PRODUCTS.get(value.lower())
    if product is not None:
        return product
    try:
        return int(value)
    except ValueError:
        names = ", ".join(PRODUCTS)
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a product id or one of: {names}"
        ) from None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mowl-to-garmin", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help=".fit files or folders")
    ap.add_argument("--product", type=parse_product, default=DEFAULT_PRODUCT,
                    help="Garmin product id or name (edge830, edge530, edge1030)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)
    product = args.product

    files = []
    for p in map(Path, args.paths):
        if p.is_dir():
            files += sorted(f for f in p.glob("*.fit")
                            if not f.stem.endswith("_garmin"))
        else:
            files.append(p)

    if not files:
        print("No .fit files found.")
        return 1

    ok = 0
    for f in files:
        try:
            new = convert(f.read_bytes(), product)
            dest = f.with_name(f.stem + "_garmin.fit")
            dest.write_bytes(new)
            print(f"OK    {f.name} -> {dest.name}")
            ok += 1
        except Exception as e:
            print(f"FAIL  {f.name}: {e}")
    print(f"\n{ok}/{len(files)} converted. Upload the *_garmin.fit files "
          "to Garmin Connect (web: Import Data).")
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
