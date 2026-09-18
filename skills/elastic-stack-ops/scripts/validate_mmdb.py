#!/usr/bin/env python3
"""Validate MaxMind .mmdb files by reading the format metadata.

Usage: python3 validate_mmdb.py GeoLite2-ASN.mmdb.tmp GeoLite2-City.mmdb.tmp
Exit 0 if all valid, 1 otherwise. Stdlib only — scp to the target host and run.

Why: a download can 200-OK with an HTML error page or truncated body. Before
promoting a *.mmdb.tmp to the live filename the collector loads (a wrong file
PANICs the collector), confirm the MaxMind magic marker + database_type.
"""
import sys

MARKER = b"\xab\xcd\xefMaxMind.com"


def read_meta(path):
    with open(path, "rb") as fh:
        data = fh.read()
    i = data.rfind(MARKER)
    if i < 0:
        return None, "sem marker MaxMind (arquivo invalido/truncado/HTML)"
    meta = data[i + len(MARKER):]
    out = {"size": len(data)}
    k = meta.find(b"database_type")
    if k >= 0:
        seg = meta[k:k + 80]
        out["type_blob"] = "".join(chr(c) for c in seg if 32 <= c < 127)
    return out, None


ok = True
for f in sys.argv[1:]:
    meta, err = read_meta(f)
    if err:
        print(f"{f}: INVALID - {err}")
        ok = False
    else:
        print(f"{f}: VALID mmdb | {meta['size']}B | {meta.get('type_blob', '')[:50]}")

sys.exit(0 if ok else 1)
