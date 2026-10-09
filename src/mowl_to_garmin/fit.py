"""Rewrite the device fields of a FIT file so it looks Garmin-recorded.

Only the device fields are changed (manufacturer + product in the file_id
message, and in the "creator" device_info message). Everything else - heart
rate, power, cadence, laps, timestamps - is copied byte for byte.
"""

import struct

GARMIN = 1  # FIT manufacturer id for Garmin

# A few Garmin product ids from the FIT SDK. Edge 830 is the default.
PRODUCTS = {
    "edge830": 3122,
    "edge530": 3121,
    "edge1030": 2713,
}
DEFAULT_PRODUCT = PRODUCTS["edge830"]

MSG_FILE_ID = 0
MSG_DEVICE_INFO = 23
UINT16 = 0x84  # FIT base type uint16

CRC_TABLE = [
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
]


def fit_crc(data, crc=0):
    for byte in data:
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[byte & 0xF]
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return crc


class Definition:
    def __init__(self, global_num, big_endian, fields, dev_size, extra):
        self.global_num = global_num
        self.big_endian = big_endian
        self.fields = fields          # list of (num, size, base_type)
        self.dev_size = dev_size      # total bytes of developer fields
        self.extra = extra            # bytes added after each data message's fields


def convert(raw: bytes, product: int):
    hdr_size = raw[0]
    if raw[8:12] != b".FIT":
        raise ValueError("not a FIT file")
    data_size = struct.unpack_from("<I", raw, 4)[0]
    body = raw[hdr_size:hdr_size + data_size]

    out = bytearray()
    defs = {}
    patched = 0
    pos = 0

    while pos < len(body):
        rh = body[pos]
        pos += 1

        if rh & 0x80:  # compressed-timestamp data message
            local = (rh >> 5) & 0x03
            is_def = False
        else:
            local = rh & 0x0F
            is_def = bool(rh & 0x40)

        if is_def:
            has_dev = bool(rh & 0x20)
            start = pos
            arch = body[pos + 1]
            big = arch == 1
            gnum = struct.unpack_from(">H" if big else "<H", body, pos + 2)[0]
            nf = body[pos + 4]
            pos += 5
            fields = []
            for _ in range(nf):
                fields.append(tuple(body[pos:pos + 3]))
                pos += 3
            dev_size = 0
            dev_bytes = b""
            if has_dev:
                ndev = body[pos]
                dev_bytes = body[pos:pos + 1 + 3 * ndev]
                for i in range(ndev):
                    dev_size += body[pos + 1 + 3 * i + 1]
                pos += 1 + 3 * ndev

            # file_id without manufacturer/product fields: add them
            extra = b""
            new_fields = list(fields)
            if gnum == MSG_FILE_ID:
                nums = {f[0] for f in fields}
                fmt = ">H" if big else "<H"
                if 1 not in nums:
                    new_fields.append((1, 2, UINT16))
                    extra += struct.pack(fmt, GARMIN)
                if 2 not in nums:
                    new_fields.append((2, 2, UINT16))
                    extra += struct.pack(fmt, product)

            defs[local] = Definition(gnum, big, fields, dev_size, extra)

            out.append(rh)
            out += body[start:start + 4]          # reserved, arch, global num
            out.append(len(new_fields))
            for f in new_fields:
                out += bytes(f)
            out += dev_bytes
            continue

        d = defs.get(local)
        if d is None:
            raise ValueError(f"data message for undefined local type {local}")
        fsize_total = sum(f[1] for f in d.fields)
        size = fsize_total + d.dev_size
        msg = bytearray(body[pos:pos + size])
        pos += size

        fmt = ">H" if d.big_endian else "<H"
        offsets, off = {}, 0
        for num, fsize, _ in d.fields:
            offsets[num] = (off, fsize)
            off += fsize

        def put(num, value):
            if num in offsets and offsets[num][1] == 2:
                struct.pack_into(fmt, msg, offsets[num][0], value)
                return True
            return False

        if d.global_num == MSG_FILE_ID:
            put(1, GARMIN)
            put(2, product)
            patched += 1
        elif d.global_num == MSG_DEVICE_INFO:
            # device_index 0 = the device that created the file
            idx = offsets.get(0)
            if idx is None or msg[idx[0]] == 0:
                if put(2, GARMIN) | put(4, product):
                    patched += 1

        out.append(rh)
        out += msg[:fsize_total]
        out += d.extra                        # added fields precede developer fields
        out += msg[fsize_total:]

    if patched == 0:
        raise ValueError("no file_id message found")

    header = bytearray(raw[:hdr_size])
    struct.pack_into("<I", header, 4, len(out))
    if hdr_size >= 14:
        struct.pack_into("<H", header, 12, fit_crc(header[:12]))
    result = bytes(header) + bytes(out)
    return result + struct.pack("<H", fit_crc(result))
