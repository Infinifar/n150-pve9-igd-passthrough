#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Build a minimal IGD initialization option ROM, not a complete OVMF or GOP.
set -eo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
build_dir="$repo_dir/build"
edk_dir=""
while (($#)); do
  case "$1" in
    --work-dir) build_dir=$2; shift 2 ;;
    --edk2-source) edk_dir=$2; shift 2 ;;
    --help)
      printf '%s\n' 'Usage: bash scripts/build-rom.sh [--work-dir DIR] [--edk2-source PINNED_EDK2_DIR]' \
        'Requires git, gcc, make, python3, nasm and uuid-dev on an x86_64 Linux builder.' \
        'Without --edk2-source, pinned EDK2 and its two required submodules are fetched.' \
        'Output: WORK_DIR/artifacts/intel-igd-init-gen12-46d4.rom; no installation.'
      exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
for command in git gcc make python3 nasm; do
  command -v "$command" >/dev/null || { printf 'Missing build tool: %s\n' "$command" >&2; exit 1; }
done
[[ $(uname -m) == x86_64 ]] || { printf 'Use an x86_64 Linux builder.\n' >&2; exit 1; }
mkdir -p -- "$build_dir"
build_dir=$(cd -- "$build_dir" && pwd)
edk_commit=2970e5699ba6267f3384ffab20f96647578aebc8
mipi_commit=370b5944c046bab043dd8b133727b2135af7747a
brotli_commit=e230f474b87134e8c6c85b630084c612057f253e
if [[ -z $edk_dir ]]; then
  edk_dir="$build_dir/edk2"
  if [[ ! -d $edk_dir ]]; then
    git init "$edk_dir"
    git -C "$edk_dir" fetch --depth 1 https://github.com/tianocore/edk2.git "$edk_commit"
    git -C "$edk_dir" checkout --detach FETCH_HEAD
    git -C "$edk_dir" submodule update --init --depth 1 \
      MdePkg/Library/MipiSysTLib/mipisyst MdeModulePkg/Library/BrotliCustomDecompressLib/brotli
  fi
fi
edk_dir=$(cd -- "$edk_dir" && pwd)
[[ $(git -C "$edk_dir" rev-parse HEAD) == "$edk_commit" ]] || { printf 'EDK2 commit mismatch.\n' >&2; exit 1; }
[[ $(git -C "$edk_dir/MdePkg/Library/MipiSysTLib/mipisyst" rev-parse HEAD) == "$mipi_commit" ]] || { printf 'MIPI commit mismatch.\n' >&2; exit 1; }
[[ $(git -C "$edk_dir/MdeModulePkg/Library/BrotliCustomDecompressLib/brotli" rev-parse HEAD) == "$brotli_commit" ]] || { printf 'Brotli commit mismatch.\n' >&2; exit 1; }
# Rebuilds may replace only the four Intel files and our DSC. Refuse other edits.
dirty=$(git -C "$edk_dir" status --porcelain --untracked-files=no --ignore-submodules=all)
[[ -z $dirty ]] || { printf 'Tracked EDK2 files were modified; use a clean build tree.\n%s\n' "$dirty" >&2; exit 1; }
python3 "$repo_dir/scripts/prepare-igd-source.py" --edk2 "$edk_dir" --repo "$repo_dir"
cd -- "$edk_dir"
# shellcheck disable=SC1091
. ./edksetup.sh BaseTools > "$build_dir/edksetup.log" 2>&1
if ! make -C BaseTools/Source/C -j2 GenFw EfiRom > "$build_dir/basetools.log" 2>&1; then
  tail -n 70 "$build_dir/basetools.log"; exit 1
fi
if ! build -n 2 -a X64 -b DEBUG -t GCC -p IntelIgdInit.dsc > "$build_dir/driver.log" 2>&1; then
  tail -n 70 "$build_dir/driver.log"; exit 1
fi
mkdir -p -- "$build_dir/artifacts"
efi=Build/IntelIgdInit/DEBUG_GCC/X64/IgdAssignmentDxe.efi
rom="$build_dir/artifacts/intel-igd-init-gen12-46d4.rom"
EfiRom -f 0x8086 -i 0x46d4 -e "$efi" -o "$rom"
EfiRom -d "$rom" | tee "$build_dir/artifacts/rom-header.txt"
cp -- "$efi" "$build_dir/artifacts/IgdAssignmentDxe.efi"
sha256sum "$rom" "$build_dir/artifacts/IgdAssignmentDxe.efi" | tee "$build_dir/artifacts/SHA256SUMS"
printf 'ROM_READY=%s\n' "$rom"
printf 'Build only. The PVE apply script uses the archived, hash-pinned ROM; see docs/BUILD.md for local rebuilds.\n'
