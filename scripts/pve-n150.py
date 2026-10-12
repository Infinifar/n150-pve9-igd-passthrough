#!/usr/bin/env python3
"""Small, explicit PVE 9.2 / QEMU 11 N150 passthrough operations.

No bootloader, driver binding, package installation or forced VM shutdown.
Configuration writes require a stopped VM and --apply; start is separate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

GPU = "0000:00:02.0"
GPU_ID = "0x46d4"
BASE_PCI = f"{GPU},pcie=1"
ROM_NAME = "intel-igd-init-gen12-46d4.rom"
ROM_SHA = "256f9d45b79c79b50ad13d79787edae5af7c6dc830a762110ad6e94f913e0eef"
ROM_PCI = f"{BASE_PCI},romfile={ROM_NAME}"
ROOT_ARGS = "-set device.hostpci0.bus=pcie.0 -set device.hostpci0.addr=0x2"
REPO = Path(__file__).resolve().parents[1]


class Refused(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_config(text: str) -> dict[str, str]:
    return dict(line.split(": ", 1) for line in text.splitlines()
                if ": " in line and not line.startswith("#"))


class Host:
    def __init__(self, config_root=Path("/etc/pve/qemu-server"),
                 sys_root=Path("/sys"), backup_root=Path("/root/n150-pve-backups"),
                 firmware_root=Path("/usr/share/kvm")):
        self.config_root = config_root
        self.sys_root = sys_root
        self.backup_root = backup_root
        self.firmware_root = firmware_root

    def run(self, *argv: str) -> str:
        result = subprocess.run(argv, text=True, capture_output=True)
        if result.returncode:
            raise Refused(f"Command failed ({result.returncode}): {' '.join(argv)}\n"
                          f"{result.stdout}{result.stderr}")
        return result.stdout + result.stderr

    def config_path(self, vmid: int) -> Path:
        path = self.config_root / f"{vmid}.conf"
        if not path.is_file():
            raise Refused(f"VM config does not exist: {path}")
        if "[PENDING]" in path.read_text():
            raise Refused("VM has pending changes. Resolve them before using this script.")
        return path

    def config(self, vmid: int) -> dict[str, str]:
        self.config_path(vmid)
        cfg = parse_config(self.run("qm", "config", str(vmid)))
        if cfg.get("lock") or cfg.get("template") == "1":
            raise Refused("VM is locked or is a template.")
        return cfg

    def stopped(self, vmid: int) -> None:
        if self.run("qm", "status", str(vmid)).strip() != "status: stopped":
            raise Refused("VM must be stopped. Shut down Windows normally, then retry.")

    def available_mib(self) -> int:
        meminfo = Path("/proc/meminfo").read_text()
        return int(re.search(r"^MemAvailable:\s+(\d+)", meminfo, re.M)[1]) // 1024

    def preflight(self, vmid: int) -> dict[str, str]:
        cfg = self.config(vmid)
        version = self.run("pveversion")
        qemu = self.run("dpkg-query", "-W", "-f=${Version}", "pve-qemu-kvm").strip()
        if not re.search(r"pve-manager/9\.2\.", version) or not re.match(r"(?:\d+:)?11\.", qemu):
            raise Refused("This recipe requires PVE 9.2 and official-packaged QEMU 11.")
        integrity = self.run("dpkg", "-V", "pve-qemu-kvm").strip()
        if integrity:
            raise Refused(f"QEMU package file integrity differs:\n{integrity}")
        if cfg.get("bios") != "ovmf" or not cfg.get("efidisk0"):
            raise Refused("An existing, bootable OVMF VM with an EFI disk is required.")
        if cfg.get("machine") != "pc-q35-11.0":
            raise Refused("Set and verify pc-q35-11.0 manually before continuing.")
        if cfg.get("vga", "std").split(",", 1)[0] in {"none", "serial0", "serial1", "serial2", "serial3"}:
            raise Refused("Keep a virtual display for observation in this recipe.")
        pci = self.sys_root / "bus/pci/devices" / GPU
        if not pci.is_dir() or (pci / "vendor").read_text().strip() != "0x8086" or (pci / "device").read_text().strip() != GPU_ID:
            raise Refused(f"Expected N150 GPU {GPU} [8086:46d4].")
        if not (pci / "driver").exists() or (pci / "driver").resolve().name != "vfio-pci":
            raise Refused("GPU is not already bound to vfio-pci. No live rebinding is attempted.")
        group = pci / "iommu_group"
        if not group.exists() or sorted(p.name for p in (group / "devices").iterdir()) != [GPU]:
            raise Refused("GPU must be the only member of its IOMMU group.")
        # Refuse devices already assigned to another VM, including stopped VMs.
        for other in self.config_root.glob("*.conf"):
            if other.stem == str(vmid):
                continue
            for key, val in parse_config(other.read_text()).items():
                if key.startswith("hostpci") and re.search(r"(?:0000:)?00:02(?:\.0)?(?:[,;]|$)", val):
                    raise Refused(f"GPU is referenced by another VM: {other.stem}.")
        if any(k.startswith("hostpci") and k != "hostpci0" for k in cfg):
            raise Refused("This minimal recipe expects only hostpci0. Review other PCI devices manually.")
        if cfg.get("hostpci0") not in {None, BASE_PCI, ROM_PCI}:
            raise Refused("hostpci0 has unrecognized options/device; it will not be overwritten.")
        if cfg.get("args") not in {None, "", ROOT_ARGS}:
            raise Refused("Existing custom QEMU args need manual review; they will not be overwritten.")
        return cfg

    def backup(self, vmid: int, action: str) -> Path:
        parent = self.backup_root / str(vmid)
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        directory = Path(tempfile.mkdtemp(prefix=f"{stamp}-{action}-", dir=parent))
        os.chmod(directory, 0o700)
        shutil.copyfile(self.config_path(vmid), directory / "before.conf")
        (directory / "showcmd.before.txt").write_text(self.run("qm", "showcmd", str(vmid), "--pretty"))
        meta = {"vmid": vmid, "action": action, "before_sha256": digest(directory / "before.conf")}
        (directory / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
        print(f"BACKUP={directory}")
        return directory

    def finish(self, directory: Path, vmid: int) -> None:
        shutil.copyfile(self.config_path(vmid), directory / "after.conf")
        meta_path = directory / "metadata.json"
        meta = json.loads(meta_path.read_text())
        meta["after_sha256"] = digest(directory / "after.conf")
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
        try:
            (directory / "showcmd.after.txt").write_text(self.run("qm", "showcmd", str(vmid), "--pretty"))
        except Refused as exc:
            (directory / "showcmd.after.error.txt").write_text(str(exc))
            raise
        print(f"Rollback: python3 scripts/pve-n150.py rollback --vmid {vmid} --backup {directory} --apply")

    def install_rom(self) -> None:
        source = REPO / "firmware" / ROM_NAME
        if not source.is_file() or digest(source) != ROM_SHA:
            raise Refused("Bundled ROM is missing or SHA256 mismatched.")
        destination = self.firmware_root / ROM_NAME
        if destination.exists():
            if digest(destination) != ROM_SHA:
                raise Refused("A different ROM already exists at the target path. Not overwritten.")
            return
        if not self.firmware_root.is_dir():
            raise Refused("PVE ROM directory is missing.")
        fd, name = tempfile.mkstemp(prefix=f".{ROM_NAME}.", dir=self.firmware_root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(source.read_bytes())
            os.chmod(name, 0o644)
            os.replace(name, destination)
        finally:
            if Path(name).exists():
                Path(name).unlink()

    def inspect(self, vmid: int) -> None:
        cfg = self.preflight(vmid)
        pci = self.sys_root / "bus/pci/devices" / GPU
        print(self.run("qm", "status", str(vmid)), end="")
        print(self.run("pveversion"), end="")
        print(self.run("dpkg-query", "-W", "-f=${Version}\n", "pve-qemu-kvm"), end="")
        print(f"GPU driver: {(pci / 'driver').resolve().name}; IOMMU group: {(pci / 'iommu_group').resolve().name}")
        print(f"Host MemAvailable: {self.available_mib()} MiB")
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        print(self.run("qm", "showcmd", str(vmid), "--pretty"), end="")

    def start(self, vmid: int, apply: bool) -> None:
        cfg = self.preflight(vmid)
        self.stopped(vmid)
        if cfg.get("hostpci0") == ROM_PCI:
            installed = self.firmware_root / ROM_NAME
            if not installed.is_file() or digest(installed) != ROM_SHA:
                raise Refused("Configured ROM is missing or altered in /usr/share/kvm.")
        needed = int(cfg["memory"]) + 256
        available = self.available_mib()
        if available < needed:
            raise Refused(f"MemAvailable {available} MiB < guest RAM + 256 MiB ({needed}); free host RAM first.")
        if not apply:
            print(f"PLAN: start VM {vmid}; available {available} MiB, required >= {needed} MiB. Add --apply.")
            return
        directory = self.backup(vmid, "start")
        self.finish(directory, vmid)
        try:
            output = self.run("qm", "start", str(vmid))
            (directory / "start.log").write_text(output)
            print(output, end="")
            print(self.run("qm", "status", str(vmid)), end="")
        except Refused as exc:
            (directory / "start.log").write_text(str(exc))
            (directory / "showcmd.failed.txt").write_text(self.run("qm", "showcmd", str(vmid), "--pretty"))
            raise Refused(f"{exc}\nLogs: {directory}. No compatibility flags or forced stop were added.") from exc

    def change(self, action: str, vmid: int, apply: bool, usb_port=None, memory_mib=None) -> None:
        cfg = self.preflight(vmid)
        self.stopped(vmid)
        update: dict[str, str] = {}
        install_needed = False
        if action == "stage1":
            if cfg.get("args") or cfg.get("hostpci0") == ROM_PCI:
                raise Refused("Use rollback to return to Stage 1; this action never strips a later working setup.")
            update = {"hostpci0": BASE_PCI}
        elif action == "rom":
            if cfg.get("hostpci0") not in {BASE_PCI, ROM_PCI}:
                raise Refused("Apply and test Stage 1 first.")
            update = {"hostpci0": ROM_PCI}
            if digest(REPO / "firmware" / ROM_NAME) != ROM_SHA:
                raise Refused("Bundled ROM SHA256 mismatched.")
            installed = self.firmware_root / ROM_NAME
            if installed.exists() and digest(installed) != ROM_SHA:
                raise Refused("A different ROM already exists at the target path. Not overwritten.")
            install_needed = not installed.exists()
        elif action == "root-pci":
            if cfg.get("hostpci0") != ROM_PCI:
                raise Refused("Test the N150 ROM before changing PCI placement.")
            if re.search(r"bus=pcie\.0,addr=0x0?2(?:[.,'\s]|$)", self.run("qm", "showcmd", str(vmid), "--pretty")):
                raise Refused("Guest root slot 2 appears occupied. Review the actual command before proceeding.")
            update = {"args": ROOT_ARGS}
        elif action == "usb":
            if not usb_port or not re.fullmatch(r"\d+-\d+(?:\.\d+)*", usb_port):
                raise Refused("Specify a physical USB port such as --usb-port 3-5.")
            usb = self.sys_root / "bus/usb/devices" / usb_port
            if not usb.is_dir() or (usb / "idVendor").read_text().strip() != "046d" or (usb / "idProduct").read_text().strip() != "c534":
                raise Refused("This port must contain the tested Logitech 046d:c534 receiver.")
            target = f"host={usb_port}"
            if cfg.get("usb0") not in {None, target}:
                raise Refused("usb0 is already used by a different device; not overwritten.")
            for conf in self.config_root.glob("*.conf"):
                if conf.stem != str(vmid) and any(k.startswith("usb") and v.split(",", 1)[0] == target
                                                  for k, v in parse_config(conf.read_text()).items()):
                    raise Refused(f"USB port is assigned to VM {conf.stem}.")
            update = {"usb0": target}
        elif action == "memory":
            if memory_mib is None or not 1024 <= memory_mib <= 65536:
                raise Refused("Specify --memory-mib between 1024 and 65536 (tested: 4096).")
            if cfg.get("balloon", "0") != "0":
                raise Refused("Review balloon settings manually before changing fixed guest RAM.")
            update = {"memory": str(memory_mib)}
        else:
            raise Refused(f"Unknown action: {action}")
        update = {k: v for k, v in update.items() if cfg.get(k) != v}
        if not update and not install_needed:
            print("Already configured; no changes.")
            return
        print("PLAN: " + json.dumps(update, ensure_ascii=False))
        if not apply:
            print("No changes made. Add --apply to apply this one stage.")
            return
        directory = self.backup(vmid, action)
        try:
            if action == "rom":
                self.install_rom()
            if update:
                command = ["qm", "set", str(vmid)]
                for key, value in update.items():
                    command.extend([f"--{key}", value])
                print(self.run(*command), end="")
        finally:
            self.finish(directory, vmid)

    def rollback(self, vmid: int, directory: Path, apply: bool) -> None:
        self.stopped(vmid)
        path = self.config_path(vmid)
        meta = json.loads((directory / "metadata.json").read_text())
        if meta.get("vmid") != vmid or meta.get("before_sha256") != digest(directory / "before.conf"):
            raise Refused("Backup VMID or before.conf hash does not match metadata.")
        if meta.get("after_sha256") != digest(path):
            raise Refused("VM config changed after this checkpoint. Review differences manually; no overwrite.")
        print(f"PLAN: restore VM {vmid} config from {directory / 'before.conf'} (disks are not restored).")
        if not apply:
            print("No changes made. Add --apply to restore.")
            return
        checkpoint = self.backup(vmid, "rollback")
        shutil.copyfile(directory / "before.conf", path)
        self.finish(checkpoint, vmid)
        print("Config restored. VM remains stopped; ROM files retained.")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=["inspect", "stage1", "rom", "root-pci", "usb", "memory", "start", "rollback"])
    result.add_argument("--vmid", type=int, required=True)
    result.add_argument("--apply", action="store_true")
    result.add_argument("--usb-port")
    result.add_argument("--memory-mib", type=int)
    result.add_argument("--backup", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.vmid < 100:
        print("VMID must be >= 100.", file=sys.stderr)
        return 2
    if sys.platform != "linux" or os.geteuid() != 0:
        print("Run on the PVE host as root. --help works on other systems.", file=sys.stderr)
        return 2
    host = Host()
    try:
        if args.action == "inspect":
            host.inspect(args.vmid)
        elif args.action == "start":
            host.start(args.vmid, args.apply)
        elif args.action == "rollback":
            if not args.backup:
                raise Refused("rollback requires --backup CHECKPOINT_DIRECTORY.")
            host.rollback(args.vmid, args.backup.resolve(), args.apply)
        else:
            host.change(args.action, args.vmid, args.apply, args.usb_port, args.memory_mib)
    except (Refused, OSError, ValueError, KeyError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
