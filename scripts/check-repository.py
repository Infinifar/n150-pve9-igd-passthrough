#!/usr/bin/env python3
"""Check release files, relative Markdown links, ROM structure and known private markers."""
import hashlib
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "build", "__pycache__", "private-evidence"}
files = [p for p in ROOT.rglob("*") if p.is_file() and not any(s in EXCLUDED for s in p.relative_to(ROOT).parts)]
problems = []
private_patterns = [
    r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
    r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
]
for path in files:
    if path.stat().st_size > 1024 * 1024:
        problems.append(f"Unexpected large file: {path.relative_to(ROOT)}")
    if path.suffix == ".rom":
        continue
    text = path.read_text(encoding="utf-8")
    if path.name != "check-repository.py" and any(re.search(p, text, re.I) for p in private_patterns):
        problems.append(f"Private marker found: {path.relative_to(ROOT)} (value suppressed)")
    if path.suffix not in {".patch", ".dsc"} and path.name != "check-repository.py":
        if re.search(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", text, re.I):
            problems.append(f"Unexpected machine UUID: {path.relative_to(ROOT)}")
        for mac in re.findall(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", text, re.I):
            if mac.lower() != "00:11:22:33:44:55":
                problems.append(f"Unexpected machine MAC: {path.relative_to(ROOT)}")
    if path.suffix == ".md":
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).exists():
                problems.append(f"Broken link in {path.relative_to(ROOT)}: {target}")
rom = ROOT / "firmware/intel-igd-init-gen12-46d4.rom"
data = rom.read_bytes()
expected = (ROOT / "firmware/SHA256SUMS").read_text().split()[0]
if hashlib.sha256(data).hexdigest() != expected:
    problems.append("ROM SHA256 mismatch")
if data[:2] != b"\x55\xaa":
    problems.append("Option ROM signature mismatch")
pcir = struct.unpack_from("<H", data, 0x18)[0]
if data[pcir:pcir + 4] != b"PCIR" or struct.unpack_from("<HH", data, pcir + 4) != (0x8086, 0x46d4):
    problems.append("ROM PCI identifier mismatch")
if problems:
    raise SystemExit("\n".join(problems))
print(f"Checked {len(files)} release files: relative links, private markers, size, ROM SHA256/PCIR OK.")
