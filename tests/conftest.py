import struct

import pytest

from mowl_to_garmin.fit import fit_crc

UINT8, UINT16, UINT32 = 0x02, 0x84, 0x86


def definition(local, global_num, fields):
    """Little-endian definition message; fields = [(num, size, base_type)]."""
    out = bytes([0x40 | local, 0, 0]) + struct.pack("<H", global_num) + bytes([len(fields)])
    for f in fields:
        out += bytes(f)
    return out


def data(local, payload):
    return bytes([local]) + payload


def build_fit(records: bytes) -> bytes:
    header = bytearray(struct.pack("<BBHI4s", 14, 0x20, 2132, len(records), b".FIT"))
    header += struct.pack("<H", fit_crc(header))
    body = bytes(header) + records
    return body + struct.pack("<H", fit_crc(body))


def sample_records(with_device_fields=True):
    """file_id (+ optional manufacturer/product), creator device_info, one record."""
    if with_device_fields:
        fid = definition(0, 0, [(0, 1, UINT8), (1, 2, UINT16), (2, 2, UINT16)])
        fid += data(0, struct.pack("<BHH", 4, 255, 42))  # type=activity, mfr=development
    else:
        fid = definition(0, 0, [(0, 1, UINT8), (4, 4, UINT32)])
        fid += data(0, struct.pack("<BI", 4, 1_000_000))
    dev = definition(1, 23, [(0, 1, UINT8), (2, 2, UINT16), (4, 2, UINT16)])
    dev += data(1, struct.pack("<BHH", 0, 255, 42))   # creator
    dev += data(1, struct.pack("<BHH", 1, 255, 7))    # sensor, must stay untouched
    rec = definition(2, 20, [(3, 1, UINT8)])          # record.heart_rate
    rec += data(2, bytes([150]))
    return fid + dev + rec


@pytest.fixture
def fit_bytes():
    return build_fit(sample_records())
