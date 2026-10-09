import struct

import pytest

from mowl_to_garmin.fit import DEFAULT_PRODUCT, GARMIN, PRODUCTS, convert, fit_crc

from .conftest import UINT8, UINT16, build_fit, data, definition, sample_records


def parse(raw):
    """Minimal parser: yields (global_num, {field_num: bytes}) for each data message."""
    hdr_size = raw[0]
    size = struct.unpack_from("<I", raw, 4)[0]
    body = raw[hdr_size:hdr_size + size]
    defs, pos = {}, 0
    while pos < len(body):
        rh = body[pos]
        pos += 1
        local = rh & 0x0F
        if rh & 0x40:
            gnum = struct.unpack_from("<H", body, pos + 2)[0]
            nf = body[pos + 4]
            pos += 5
            fields = [tuple(body[pos + 3 * i:pos + 3 * i + 3]) for i in range(nf)]
            pos += 3 * nf
            defs[local] = (gnum, fields)
        else:
            gnum, fields = defs[local]
            values = {}
            for num, fsize, _ in fields:
                values[num] = body[pos:pos + fsize]
                pos += fsize
            yield gnum, values


def u16(b):
    return struct.unpack("<H", b)[0]


def assert_crcs_valid(raw):
    assert fit_crc(raw[:12]) == u16(raw[12:14])
    assert fit_crc(raw) == 0  # CRC over data + trailing CRC is zero


def test_patches_existing_device_fields(fit_bytes):
    out = convert(fit_bytes, PRODUCTS["edge530"])
    assert_crcs_valid(out)
    msgs = list(parse(out))

    file_id = next(v for g, v in msgs if g == 0)
    assert u16(file_id[1]) == GARMIN
    assert u16(file_id[2]) == PRODUCTS["edge530"]

    creator, sensor = [v for g, v in msgs if g == 23]
    assert (u16(creator[2]), u16(creator[4])) == (GARMIN, PRODUCTS["edge530"])
    assert (u16(sensor[2]), u16(sensor[4])) == (255, 7)

    record = next(v for g, v in msgs if g == 20)
    assert record[3] == bytes([150])


def test_same_length_when_fields_exist(fit_bytes):
    assert len(convert(fit_bytes, 3122)) == len(fit_bytes)


def test_adds_missing_device_fields():
    raw = build_fit(sample_records(with_device_fields=False))
    out = convert(raw, 3122)
    assert_crcs_valid(out)
    file_id = next(v for g, v in parse(out) if g == 0)
    assert u16(file_id[1]) == GARMIN
    assert u16(file_id[2]) == 3122
    assert struct.unpack("<I", file_id[4])[0] == 1_000_000


def test_rejects_non_fit():
    with pytest.raises(ValueError, match="not a FIT file"):
        convert(b"\x0e" + b"\x00" * 20, 3122)


def test_crc_matches_known_check_value():
    # FIT uses CRC-16/ARC, whose standard check value for "123456789" is 0xBB3D
    assert fit_crc(b"123456789") == 0xBB3D
    assert fit_crc(b"") == 0


def test_crc_can_be_computed_incrementally():
    assert fit_crc(b"6789", fit_crc(b"12345")) == fit_crc(b"123456789")


def test_default_product_is_edge830():
    assert DEFAULT_PRODUCT == PRODUCTS["edge830"] == 3122


def test_big_endian_messages():
    # definition: reserved, arch=1 (big endian), global 0, 3 fields
    fid = bytes([0x40, 0, 1]) + struct.pack(">H", 0) + bytes([3])
    fid += bytes([0, 1, UINT8, 1, 2, UINT16, 2, 2, UINT16])
    fid += data(0, struct.pack(">BHH", 4, 255, 42))
    out = convert(build_fit(fid), 3122)
    assert_crcs_valid(out)
    payload = out[-2 - 5:-2]
    assert struct.unpack(">BHH", payload) == (4, GARMIN, 3122)


def test_compressed_timestamp_messages_are_copied():
    compressed = bytes([0x80 | (2 << 5) | 5, 151])  # local type 2, time offset 5
    raw = build_fit(sample_records() + compressed)
    out = convert(raw, 3122)
    assert_crcs_valid(out)
    assert out[-4:-2] == compressed
    assert len(out) == len(raw)


def test_developer_fields_are_copied():
    # record definition with one normal field and one 2-byte developer field
    rec = bytes([0x40 | 0x20 | 3, 0, 0]) + struct.pack("<H", 20) + bytes([1])
    rec += bytes([3, 1, UINT8])
    rec += bytes([1, 0, 2, 0])  # 1 dev field: num 0, size 2, dev index 0
    rec += data(3, bytes([150, 0xAB, 0xCD]))
    raw = build_fit(sample_records() + rec)
    out = convert(raw, 3122)
    assert_crcs_valid(out)
    assert out[-2 - len(rec):-2] == rec


def test_twelve_byte_header():
    records = sample_records()
    header = struct.pack("<BBHI4s", 12, 0x10, 2132, len(records), b".FIT")
    body = header + records
    out = convert(body + struct.pack("<H", fit_crc(body)), 3122)
    assert out[0] == 12
    assert fit_crc(out) == 0
    file_id = next(v for g, v in parse(out) if g == 0)
    assert u16(file_id[1]) == GARMIN


def test_trailing_bytes_after_data_are_ignored(fit_bytes):
    assert convert(fit_bytes + b"junk", 3122) == convert(fit_bytes, 3122)


def test_only_device_bytes_differ(fit_bytes):
    out = convert(fit_bytes, 3122)
    changed = [i for i, (a, b) in enumerate(zip(fit_bytes[:-2], out[:-2], strict=True)) if a != b]
    # manufacturer (low byte; 255 -> 1) and product in file_id, then in creator device_info
    assert changed == [31, 33, 34, 52, 54, 55]


def test_data_before_definition_is_rejected():
    with pytest.raises(ValueError, match="undefined local type 5"):
        convert(build_fit(data(5, b"\x00")), 3122)


def test_file_without_file_id_is_rejected():
    rec = definition(2, 20, [(3, 1, UINT8)]) + data(2, bytes([150]))
    with pytest.raises(ValueError, match="no file_id message found"):
        convert(build_fit(rec), 3122)


@pytest.mark.parametrize("product", sorted(PRODUCTS.values()))
def test_every_preset_is_written(fit_bytes, product):
    file_id = next(v for g, v in parse(convert(fit_bytes, product)) if g == 0)
    assert u16(file_id[2]) == product


def test_added_fields_go_before_developer_fields():
    # file_id with a developer field but no manufacturer/product
    fid = bytes([0x40 | 0x20, 0, 0]) + struct.pack("<H", 0) + bytes([1])
    fid += bytes([0, 1, UINT8])
    fid += bytes([1, 0, 2, 0])  # 1 dev field: num 0, size 2, dev index 0
    fid += data(0, bytes([4, 0xAB, 0xCD]))
    out = convert(build_fit(fid), 3122)
    assert_crcs_valid(out)
    # data message: type, manufacturer, product, then the developer bytes
    assert out[-2 - 7:-2] == struct.pack("<BHH", 4, GARMIN, 3122) + b"\xab\xcd"
