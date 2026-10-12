#!/usr/bin/env python3
"""Extract Intel's four added source files and apply the archived N150 patch."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess

ALLOWED = {
    "OvmfPkg/Include/IndustryStandard/AssignedIgd.h",
    "OvmfPkg/Include/IndustryStandard/IgdOpRegion.h",
    "OvmfPkg/IgdAssignmentDxe/IgdAssignment.c",
    "OvmfPkg/IgdAssignmentDxe/IgdAssignment.inf",
}


def prepare(edk2: Path, repo: Path) -> None:
    sources = {}
    for name in ["Intel-IgdHeaders.patch", "Intel-IgdAssignmentDxe.patch"]:
        for block in (repo / "source" / name).read_text().split("diff --git ")[1:]:
            lines = block.splitlines()
            match = re.fullmatch(r"a/[^ ]+ b/(\S+)", lines[0])
            if not match or match[1] not in ALLOWED:
                continue
            if "--- /dev/null" not in lines:
                raise ValueError("Only Intel's added source files may be extracted.")
            text = "\n".join(line[1:] for line in lines if line.startswith("+") and not line.startswith("+++")) + "\n"
            hunk = re.search(r"@@ -0,0 \+1,(\d+) @@", block)
            if not hunk or len(text.splitlines()) != int(hunk[1]):
                raise ValueError(f"Truncated Intel source: {match[1]}")
            sources[match[1]] = text
    if set(sources) != ALLOWED:
        raise ValueError("Intel patches do not contain all four expected files.")
    for name, text in sources.items():
        target = edk2 / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    shutil.copyfile(repo / "source" / "IntelIgdInit.dsc", edk2 / "IntelIgdInit.dsc")
    subprocess.run(["git", "apply", "--check", str(repo / "source" / "intel-n150-gen12.patch")], cwd=edk2, check=True)
    subprocess.run(["git", "apply", str(repo / "source" / "intel-n150-gen12.patch")], cwd=edk2, check=True)
    print("Extracted Intel files and applied the device-specific 8086:46d4 patch.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edk2", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    prepare(args.edk2.resolve(), args.repo.resolve())
