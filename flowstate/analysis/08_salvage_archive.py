"""Salvage the truncated 384 MB datasetHackathon archive.

The download is cut off with no central directory, but every LOCAL file header survives, and
WinZip-AES is AES-CTR - a stream cipher - so a truncated prefix decrypts fine. Chain is:
  exd_download (1).zip  ->  datasetHackathon.zip.zip  (deflate, streamed)
    -> datasetHackathon.zip  (AES-256, actual method deflate)
      -> 10,216 plain deflate entries (anonymizedDataLake + exampleUserC)

Steps 1-2 are done by the one-off commands in the session log and leave
  F:\\bmw\\data\\raw\\_salvage_dataset_inner.zip
This script does step 3: walk the local headers and inflate every complete entry.
"""
import io
import os
import pickle
import re
import struct
import sys
import time
import zlib

INNER = r"F:\bmw\data\raw\_salvage_dataset_inner.zip"
OUTDIR = r"F:\bmw\data\raw\salvaged"
IDX = r"F:\bmw\data\raw\_salvage_index.pkl"

size = os.path.getsize(INNER)
if os.path.exists(IDX):
    hits = pickle.load(open(IDX, "rb"))
else:
    hits, pos, CH = [], 0, 32 << 20
    f = io.open(INNER, "rb")
    while pos < size:
        f.seek(pos); buf = f.read(CH + 4)
        if not buf:
            break
        for m in re.finditer(b"PK\x03\x04", buf):
            off = pos + m.start()
            if off + 30 > size:
                continue
            f.seek(off); hdr = f.read(30)
            ver, flags, method, mt, md, crc, csz, usz, nlen, elen = struct.unpack("<HHHHHIIIHH", hdr[4:30])
            if method not in (0, 8, 99) or not (1 <= nlen <= 300) or elen > 4096:
                continue
            nm = f.read(nlen)
            try:
                nm = nm.decode("utf-8")
            except Exception:
                continue
            if not re.fullmatch(r"[\w\-./ ()\u00c0-\u024f]+", nm):
                continue
            hits.append(dict(off=off, name=nm, method=method, flags=flags, csz=csz, usz=usz, nlen=nlen, elen=elen))
        pos += CH
    f.close()
    pickle.dump(hits, open(IDX, "wb"))

print("entries indexed: %s   source %.1f MB" % (f"{len(hits):,}", size / 1e6))
os.makedirs(OUTDIR, exist_ok=True)
f = io.open(INNER, "rb")
ok = trunc = skipped = 0
bytes_out = 0
t0 = time.time()

for i, h in enumerate(hits):
    name = h["name"]
    if name.startswith("__MACOSX") or "/._" in name or name.endswith("/"):
        skipped += 1
        continue
    dst = os.path.join(OUTDIR, name.replace("/", os.sep))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    start = h["off"] + 30 + h["nlen"] + h["elen"]
    # bound the read by the next header so a corrupt stream cannot run away
    end = hits[i + 1]["off"] if i + 1 < len(hits) else size
    f.seek(start)
    raw = f.read(min(end - start, 64 << 20))
    if h["method"] == 0:
        data, complete = raw, (i + 1 < len(hits))
    else:
        d = zlib.decompressobj(-15)
        try:
            data = d.decompress(raw)
            data += d.flush()
            complete = d.eof
        except zlib.error:
            skipped += 1
            continue
    if not data:
        skipped += 1
        continue
    io.open(dst, "wb").write(data)
    bytes_out += len(data)
    if complete:
        ok += 1
    else:
        trunc += 1
    if (i + 1) % 2000 == 0:
        print("  %6d/%d  ok=%d truncated=%d  %.0f MB out  %.0fs"
              % (i + 1, len(hits), ok, trunc, bytes_out / 1e6, time.time() - t0), flush=True)

f.close()
print("\nDONE in %.0fs" % (time.time() - t0))
print("  complete files : %s" % f"{ok:,}")
print("  truncated tail : %d  (expected: the download stops mid-entry)" % trunc)
print("  skipped        : %d  (directories, __MACOSX, empty)" % skipped)
print("  written        : %.1f MB to %s" % (bytes_out / 1e6, OUTDIR))
