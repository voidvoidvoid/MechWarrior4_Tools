#!/usr/bin/env python3
"""Read-only MW4 #VBD v4 extractor. Python 3.10+, standard library only.

Recovers stored asset bytes before the game's stateful content postprocessor.
Cipher/key provenance: passes 63/64/68; archive/LZW provenance: passes 4/68.
No game code, keys, tables, or assets are embedded in this file.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import zlib

VERSION = "1.0.0"
BASE = 0x400000
MATERIAL_SHA256 = "59adfa9a8d8bdd9b99ad99670338c5703680faffe17e2c0f71bdee01c68f0848"
MASK = 0xFFFFFFFF
DEFAULT_LIMIT = 64 * 1024 * 1024


class ExtractError(ValueError):
    """Invalid, unsupported, or unsafe input."""


def exact_read(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise ExtractError("Truncated input")
    return data


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_index(stream):
    """Parse all physical index records; retain native declared-count membership."""
    size = os.fstat(stream.fileno()).st_size
    stream.seek(0)
    magic, version, revision, boundary, count, last_id = struct.unpack(
        "<4sIIIHH", exact_read(stream, 20))
    if magic != b"#VBD" or version != 4:
        raise ExtractError("Expected #VBD archive version 4")
    if not 20 <= boundary <= size:
        raise ExtractError("Invalid payload boundary")
    # Bound index memory independently of archive size. The format uses 16-bit IDs.
    if boundary > 64 * 1024 * 1024:
        raise ExtractError("Index exceeds 64 MiB limit")
    rows = []
    while stream.tell() < boundary:
        pos = stream.tell()
        if boundary - pos < 23:
            raise ExtractError("Incomplete index record at payload boundary")
        timestamp, decoded, stored, offset, rid, n = struct.unpack(
            "<QIIIHB", exact_read(stream, 23))
        if stream.tell() + n > boundary:
            raise ExtractError("Resource name crosses payload boundary")
        name_bytes = exact_read(stream, n)
        # Undefined CP1252 bytes remain visible and are rejected by path validation.
        name = name_bytes.decode("cp1252", errors="surrogateescape")
        if offset + stored > size - boundary:
            raise ExtractError(f"Resource {len(rows)} extends beyond archive")
        rows.append(dict(ordinal=len(rows), id=rid, name=name,
                         name_hex=name_bytes.hex(), index_offset=pos,
                         timestamp_raw=timestamp, decoded_size=decoded,
                         stored_size=stored, payload_offset=offset,
                         indexed=len(rows) < count))
        if len(rows) > 65536:
            raise ExtractError("More than 65536 physical index records")
    if count > len(rows):
        raise ExtractError("Declared count exceeds complete physical records")
    return dict(version=version, revision=revision, payload_boundary=boundary,
                header_record_count=count, last_id=last_id,
                physical_records=len(rows), file_size=size), rows


def lzw_decode(data, expected):
    """MW4 LSB-first 9..12-bit LZW; strict EOF and output-length validation."""
    table = [bytes([i]) for i in range(256)] + [None] * (4096 - 256)
    bits, pos, next_code, old = 9, 0, 258, None
    out = bytearray()
    while pos + bits <= len(data) * 8:
        j, shift = divmod(pos, 8)
        code = (int.from_bytes(data[j:j + 3], "little") >> shift) & ((1 << bits) - 1)
        pos += bits
        if code == 257:
            if len(out) != expected:
                raise ExtractError(f"Decoded length {len(out)} != metadata {expected}")
            return bytes(out)
        if code == 256:
            # Entries beyond next_code are inaccessible until rewritten.
            bits, next_code, old = 9, 258, None
            continue
        if code < next_code and code < 4096 and table[code] is not None:
            word = table[code]
        elif code == next_code and old is not None and code < 4096:
            word = old + old[:1]
        else:
            raise ExtractError(f"Invalid LZW code {code} (next {next_code})")
        if len(word) > expected - len(out):
            raise ExtractError("LZW output exceeds metadata length")
        out.extend(word)
        if old is not None and next_code < 4096:
            table[next_code] = old + word[:1]
            next_code += 1
            if next_code >= 1 << bits and bits < 12:
                bits += 1
        old = word
    raise ExtractError("Missing LZW end code")


def transform(p, s, left, right):
    """Pass64 word-pair model, also used with reversed P for decryption."""
    for i in range(16):
        left ^= p[i]
        f = ((((s[left >> 24] + s[256 + ((left >> 16) & 255)]) & MASK)
              ^ s[512 + ((left >> 8) & 255)]) + s[768 + (left & 255)]) & MASK
        right ^= f
        left, right = right, left
    return right ^ p[17], left ^ p[16]


def expand_key(tables, key):
    if not 1 <= len(key) <= 56:
        raise ExtractError("Unsupported key length")
    p = list(struct.unpack_from("<18I", tables))
    s = list(struct.unpack_from("<1024I", tables, 72))
    for i in range(18):
        p[i] ^= int.from_bytes(bytes(key[(i * 4 + j) % len(key)] for j in range(4)), "big")
    left = right = 0
    for t in (p, s):
        for i in range(0, len(t), 2):
            left, right = transform(p, s, left, right)
            t[i:i + 2] = (left, right)
    return p, s


class KeySource:
    """Reads only pinned material at VAs, from a mapped image or unpacked PE32."""
    def __init__(self, path):
        self.path = Path(path)
        self.schedules = {}
        with self.path.open("rb") as f:
            size = os.fstat(f.fileno()).st_size
            # Mapped images retain MZ/PE headers too. Identify the pinned mapped
            # material first; only then attempt on-disk PE section translation.
            if size >= 0x816928 - BASE + 4168:
                f.seek(0x80B894 - BASE)
                probe_key = exact_read(f, 56).split(b"\0", 1)[0]
                f.seek(0x80B8CC - BASE)
                probe_secure = exact_read(f, 56)
                f.seek(0x816928 - BASE)
                probe_tables = exact_read(f, 4168)
                if hashlib.sha256(probe_key + probe_secure + probe_tables).hexdigest() == MATERIAL_SHA256:
                    self.keys = {"mektek": probe_key, "secure": probe_secure}
                    self.tables = probe_tables
                    self.sha256 = file_hash(self.path)
                    return
            f.seek(0)
            magic = exact_read(f, 2)
            sections = None
            if magic == b"MZ":
                f.seek(0x3C)
                pe = struct.unpack("<I", exact_read(f, 4))[0]
                if pe > size - 24:
                    raise ExtractError("Invalid PE header")
                f.seek(pe)
                if exact_read(f, 4) != b"PE\0\0":
                    raise ExtractError("Invalid PE signature")
                machine, nsec, _, _, _, opt_size, _ = struct.unpack("<HHIIIHH", exact_read(f, 20))
                if machine != 0x14C or not 1 <= nsec <= 96 or opt_size < 64:
                    raise ExtractError("Expected 32-bit x86 PE")
                opt = exact_read(f, opt_size)
                if struct.unpack_from("<H", opt)[0] != 0x10B or struct.unpack_from("<I", opt, 28)[0] != BASE:
                    raise ExtractError("Expected PE32 image base 0x00400000")
                sections = []
                for _ in range(nsec):
                    sh = exact_read(f, 40)
                    _, va, raw_size, raw_offset = struct.unpack_from("<IIII", sh, 8)
                    if raw_offset + raw_size > size:
                        raise ExtractError("PE section exceeds file")
                    sections.append((va, raw_size, raw_offset))

            def at(va, n):
                rva = va - BASE
                offset = rva
                if sections is not None:
                    matches = [off + rva - start for start, length, off in sections
                               if start <= rva and rva + n <= start + length]
                    if len(matches) != 1:
                        raise ExtractError("Required data unavailable; use recovered image.bin or unpacked analysis PE")
                    offset = matches[0]
                if offset < 0 or offset + n > size:
                    raise ExtractError("Key source is truncated or not the supported mapped image")
                f.seek(offset)
                return exact_read(f, n)

            key_region = at(0x80B894, 56)
            if b"\0" not in key_region:
                raise ExtractError("MekTek key terminator missing; unsupported key source")
            self.keys = {"mektek": key_region.split(b"\0", 1)[0],
                         "secure": at(0x80B8CC, 56)}
            self.tables = at(0x816928, 4168)
            material = self.keys["mektek"] + self.keys["secure"] + self.tables
            if hashlib.sha256(material).hexdigest() != MATERIAL_SHA256:
                raise ExtractError("Key/table profile mismatch; use the project's recovered image.bin or unpacked analysis PE")
        self.sha256 = file_hash(self.path)

    def decrypt(self, tag, ciphertext):
        if len(ciphertext) % 8:
            raise ExtractError("Ciphertext is not aligned to eight bytes")
        if tag not in self.schedules:
            p, s = expand_key(self.tables, self.keys[tag])
            self.schedules[tag] = (p[::-1], s)
        p, s = self.schedules[tag]
        result = bytearray(len(ciphertext))
        for offset in range(0, len(ciphertext), 8):
            left, right = struct.unpack_from("<II", ciphertext, offset)
            struct.pack_into("<II", result, offset, *transform(p, s, left, right))
        return bytes(result)


def decode_member(blob, row, keys, limit):
    expected = row["decoded_size"]
    if max(expected, len(blob)) > limit:
        raise ExtractError("Member exceeds --max-member-mib limit")
    if len(blob) == expected:
        return blob, dict(method="raw")
    if len(blob) > expected:
        raise ExtractError("Stored size exceeds decoded size; unsupported native raw-size mismatch")
    tag = blob[:6]
    if tag not in (b"secure", b"mektek"):
        return lzw_decode(blob, expected), dict(method="lzw")
    if len(blob) < 18:
        raise ExtractError("Truncated encrypted wrapper")
    padded, packed, crc = struct.unpack_from("<III", blob, 6)
    if padded == 0 or padded % 8 or padded != len(blob) - 18:
        raise ExtractError("Invalid wrapped ciphertext extent/alignment")
    if not 0 < packed <= padded or padded - packed >= 8:
        raise ExtractError("Invalid packed length/padding")
    if keys is None:
        raise ExtractError("Encrypted member requires --key-source")
    compressed = keys.decrypt(tag.decode("ascii"), blob[18:])[:packed]
    plain = lzw_decode(compressed, expected)
    actual_crc = zlib.crc32(plain) & MASK
    if actual_crc != crc:
        raise ExtractError(f"CRC32 mismatch: stored {crc:08x}, decoded {actual_crc:08x}")
    return plain, dict(method=tag.decode("ascii"), crc32=f"{actual_crc:08x}",
                       crc32_matches=True, packed_bytes=packed, padded_bytes=padded)


def safe_parts(name):
    path = name.replace("\\", "/")
    parts = path.split("/")
    for part in parts:
        if not part or part in (".", "..") or part.endswith((" ", ".")):
            raise ExtractError("Unsafe empty/dot/trailing-space path component")
        if any(ord(c) < 32 or 127 <= ord(c) < 160 or 0xD800 <= ord(c) <= 0xDFFF
               or c in '<>:"|?*' for c in part):
            raise ExtractError("Unsafe/control/Windows-invalid filename")
        stem = part.split(".", 1)[0].upper()
        if re.fullmatch(r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³]", stem):
            raise ExtractError("Reserved Windows device name")
    return parts


class PathPlanner:
    def __init__(self):
        self.files = set()
        self.dirs = set()

    def reserve(self, row):
        parts = safe_parts(row["name"])
        candidate = ["assets"] + parts if row["indexed"] else ["unindexed", f'{row["ordinal"]:05d}-{row["id"]:05d}'] + parts
        folded = [p.casefold() for p in candidate]
        whole = "/".join(folded)
        parents = ["/".join(folded[:i]) for i in range(1, len(folded))]
        if whole in self.files or whole in self.dirs or any(p in self.files for p in parents):
            candidate = ["duplicates", f'{row["ordinal"]:05d}-{row["id"]:05d}'] + parts
            folded = [p.casefold() for p in candidate]
            whole = "/".join(folded)
            parents = ["/".join(folded[:i]) for i in range(1, len(folded))]
        self.files.add(whole)
        self.dirs.update(parents)
        return "/".join(candidate)


def write_member(root, relative, data):
    target = root / relative
    parent = root
    for component in Path(relative).parts[:-1]:
        parent = parent / component
        if parent.is_symlink() or not parent.resolve().is_relative_to(root):
            raise ExtractError("Output parent escapes destination or is a symlink")
        parent.mkdir(exist_ok=True)
    # Fresh output root plus exclusive creation: never replace existing content.
    with target.open("xb") as f:
        try:
            f.write(data)
        except BaseException:
            f.close()
            target.unlink(missing_ok=True)
            raise


def run(args):
    archive = args.archive.resolve(strict=True)
    with archive.open("rb") as stream:
        meta, rows = read_index(stream)
        report = dict(tool_version=VERSION, archive=str(archive), archive_sha256=file_hash(archive),
                      metadata=meta, postprocessing="none; stored asset bytes", members=[])
        if args.list:
            report["members"] = rows
            print(json.dumps(report, indent=2, ensure_ascii=True))
            return 0
        keys = KeySource(args.key_source) if args.key_source else None
        report["key_source_sha256"] = keys.sha256 if keys else None
        root = None
        if not args.verify:
            if args.output is None:
                raise ExtractError("Specify --output NEW_DIRECTORY, --verify, or --list")
            root = args.output.absolute()
            # Do not accept an existing root, even an empty one or a symlink.
            root.mkdir(parents=True, exist_ok=False)
            root = root.resolve(strict=True)
        planner = PathPlanner()
        failures = successes = skipped = 0
        try:
            for original in rows:
                row = dict(original)
                report["members"].append(row)
                normalized = row["name"].replace("\\", "/").casefold()
                if (not row["indexed"] and not args.include_unindexed) or (
                    args.pattern and not any(fnmatch.fnmatchcase(normalized, p.replace("\\", "/").casefold()) for p in args.pattern)):
                    row["status"] = "skipped"
                    skipped += 1
                    continue
                try:
                    relative = planner.reserve(row)
                    if max(row["decoded_size"], row["stored_size"]) > args.max_member_mib * 1024 * 1024:
                        raise ExtractError("Member exceeds --max-member-mib limit")
                    stream.seek(meta["payload_boundary"] + row["payload_offset"])
                    blob = exact_read(stream, row["stored_size"])
                    plain, info = decode_member(blob, row, keys, args.max_member_mib * 1024 * 1024)
                    row.update(info, decoded_sha256=hashlib.sha256(plain).hexdigest(),
                               actual_decoded_size=len(plain), output_path=relative)
                    if root:
                        write_member(root, relative, plain)
                    row["status"] = "extracted" if root else "verified"
                    successes += 1
                except (ExtractError, OSError) as exc:
                    row.update(status="error", error=str(exc))
                    failures += 1
                    print(f'ERROR member {row["ordinal"]} {row["name"]!r}: {exc}', file=sys.stderr)
                if (successes + failures) % 1000 == 0:
                    print(f"Processed {successes + failures} members", file=sys.stderr)
        finally:
            report["summary"] = dict(succeeded=successes, failed=failures, skipped=skipped,
                                     complete=len(report["members"]) == len(rows) and
                                     all("status" in row for row in report["members"]))
            if root:
                with (root / "manifest.json").open("x", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=True)
                    f.write("\n")
        if args.verify:
            print(json.dumps(report, indent=2, ensure_ascii=True))
        else:
            print(f"Extracted {successes}; failed {failures}; skipped {skipped}. Manifest: {root / 'manifest.json'}")
        return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--output", type=Path, help="New directory; refuses any existing directory")
    mode.add_argument("--verify", action="store_true", help="Decode and verify without writing assets; JSON to stdout")
    mode.add_argument("--list", action="store_true", help="List all physical index records as JSON; no decoding")
    parser.add_argument("--key-source", type=Path, help="Recovered image.bin or unpacked MW4Mercs.analysis.exe")
    parser.add_argument("--include-unindexed", action="store_true", help="Also recover records beyond declared count into unindexed/")
    parser.add_argument("--pattern", action="append", help="Case-insensitive member-name glob; repeat to include alternatives")
    parser.add_argument("--max-member-mib", type=int, default=64, help="Stored/decoded per-member limit (default 64 MiB)")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)
    if args.max_member_mib < 1:
        parser.error("--max-member-mib must be positive")
    try:
        return run(args)
    except (ExtractError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted; inspect any partial output manifest before retrying in a new directory.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
