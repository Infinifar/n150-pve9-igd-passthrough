"""Exercise writes and failure handling against a fake PVE host, never a real VM."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pve_n150", ROOT / "scripts/pve-n150.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

BASE = """bios: ovmf
efidisk0: local:102/efi.qcow2,efitype=4m
machine: pc-q35-11.0
memory: 4096
balloon: 0
ide0: local:102/disk.qcow2,size=64G
net0: virtio=00:11:22:33:44:55,bridge=vmbr0
"""


class FakeHost(app.Host):
    def __init__(self, root):
        super().__init__(root / "configs", root / "sys", root / "backups", root / "roms")
        self.config_root.mkdir()
        self.firmware_root.mkdir()
        (self.config_root / "102.conf").write_text(BASE)
        pci = self.sys_root / "bus/pci/devices" / app.GPU
        (pci / "driver").mkdir(parents=True)
        (pci / "vendor").write_text("0x8086")
        (pci / "device").write_text("0x46d4")
        (pci / "iommu_group/devices" / app.GPU).mkdir(parents=True)
        self.state = "stopped"
        self.version = "11.0.3-4"
        self.driver = "vfio-pci"
        self.available = 8000
        self.fail_start = False
        self.calls = []

    def available_mib(self):
        return self.available

    def run(self, *argv):
        self.calls.append(argv)
        if argv[0] == "pveversion":
            return "pve-manager/9.2.21/build\n"
        if argv[0] == "dpkg-query":
            return self.version
        if argv[:2] == ("dpkg", "-V"):
            return ""
        if argv[:2] == ("qm", "config"):
            return (self.config_root / f"{argv[2]}.conf").read_text()
        if argv[:2] == ("qm", "status"):
            return f"status: {self.state}\n"
        if argv[:2] == ("qm", "showcmd"):
            return "kvm -device VGA,id=vga,bus=pcie.0,addr=0x1\n"
        if argv[:2] == ("qm", "set"):
            path = self.config_root / f"{argv[2]}.conf"
            cfg = app.parse_config(path.read_text())
            for i in range(3, len(argv), 2):
                cfg[argv[i][2:]] = argv[i + 1]
            path.write_text("".join(f"{k}: {v}\n" for k, v in cfg.items()))
            return "updated\n"
        if argv[:2] == ("qm", "start"):
            if self.fail_start:
                raise app.Refused("simulated QEMU start failure")
            self.state = "running"
            return "started\n"
        raise AssertionError(argv)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        # Windows cannot represent ':' in fixture directory names. Only the
        # fake sysfs pathname is normalized; real PCI option strings are intact.
        if os.name == "nt":
            gpu_patch = patch.object(app, "GPU", "0000_00_02.0")
            gpu_patch.start()
            self.addCleanup(gpu_patch.stop)
        scratch = ROOT / "build" / "test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.host = FakeHost(Path(self.temp.name))
        real_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            if path.name == "driver":
                return Path("drivers") / self.host.driver
            return real_resolve(path, *args, **kwargs)

        self.resolve_patch = patch.object(Path, "resolve", resolve)
        self.resolve_patch.start()
        self.addCleanup(self.resolve_patch.stop)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def path(self):
        return self.host.config_root / "102.conf"

    def checkpoints(self):
        return sorted((self.host.backup_root / "102").glob("*/metadata.json"))

    def add_config(self, text):
        with self.path().open("a") as stream:
            stream.write(text)

    def test_dry_run_has_no_config_or_firmware_write(self):
        before = self.path().read_bytes()
        self.host.change("stage1", 102, False)
        self.assertEqual(before, self.path().read_bytes())
        self.assertFalse(self.host.backup_root.exists())
        self.assertFalse(any(c[:2] == ("qm", "set") for c in self.host.calls))

    def test_running_vm_refused_before_write(self):
        self.host.state = "running"
        with self.assertRaisesRegex(app.Refused, "must be stopped"):
            self.host.change("memory", 102, True, memory_mib=4096)
        self.assertFalse(self.host.backup_root.exists())

    def test_stage_flow_keeps_disks_network_and_allows_exact_rollback(self):
        self.host.change("stage1", 102, True)
        self.host.change("rom", 102, True)
        self.host.change("root-pci", 102, True)
        self.host.change("memory", 102, True, memory_mib=6144)
        cfg = self.host.config(102)
        self.assertEqual(cfg["hostpci0"], app.ROM_PCI)
        self.assertEqual(cfg["args"], app.ROOT_ARGS)
        self.assertEqual(cfg["memory"], "6144")
        self.assertEqual(cfg["ide0"], app.parse_config(BASE)["ide0"])
        self.assertEqual(cfg["net0"], app.parse_config(BASE)["net0"])
        self.assertEqual(app.digest(self.host.firmware_root / app.ROM_NAME), app.ROM_SHA)
        checkpoints = self.checkpoints()
        memory_backup = next(p.parent for p in checkpoints if json.loads(p.read_text())["action"] == "memory")
        self.host.rollback(102, memory_backup, True)
        self.assertEqual(self.host.config(102)["memory"], "4096")
        self.assertEqual(self.host.config(102)["args"], app.ROOT_ARGS)

    def test_idempotence_creates_no_second_backup(self):
        self.host.change("stage1", 102, True)
        count = len(self.checkpoints())
        self.host.change("stage1", 102, True)
        self.assertEqual(count, len(self.checkpoints()))

    def test_changed_config_is_not_overwritten_by_rollback(self):
        self.host.change("stage1", 102, True)
        checkpoint = self.checkpoints()[0].parent
        self.add_config("description: later user change\n")
        with self.assertRaisesRegex(app.Refused, "changed after"):
            self.host.rollback(102, checkpoint, True)
        self.assertIn("later user change", self.path().read_text())

    def test_corrupt_backup_is_rejected(self):
        self.host.change("stage1", 102, True)
        checkpoint = self.checkpoints()[0].parent
        (checkpoint / "before.conf").write_text("damaged")
        with self.assertRaisesRegex(app.Refused, "hash"):
            self.host.rollback(102, checkpoint, True)

    def test_wrong_vmid_backup_is_rejected(self):
        self.host.change("stage1", 102, True)
        checkpoint = self.checkpoints()[0].parent
        meta = json.loads((checkpoint / "metadata.json").read_text())
        meta["vmid"] = 103
        (checkpoint / "metadata.json").write_text(json.dumps(meta))
        with self.assertRaisesRegex(app.Refused, "VMID"):
            self.host.rollback(102, checkpoint, True)

    def test_shared_iommu_group_is_rejected(self):
        group = self.host.sys_root / "bus/pci/devices" / app.GPU / "iommu_group/devices"
        (group / "another-pci-device").mkdir()
        with self.assertRaisesRegex(app.Refused, "only member"):
            self.host.preflight(102)

    def test_i915_binding_is_rejected(self):
        self.host.driver = "i915"
        with self.assertRaisesRegex(app.Refused, "vfio-pci"):
            self.host.preflight(102)

    def test_other_vm_pci_assignment_is_rejected(self):
        (self.host.config_root / "103.conf").write_text("hostpci0: 00:02.0,pcie=1\n")
        with self.assertRaisesRegex(app.Refused, "another VM"):
            self.host.preflight(102)

    def test_existing_args_are_not_overwritten(self):
        self.add_config("args: -cpu something\n")
        with self.assertRaisesRegex(app.Refused, "custom QEMU args"):
            self.host.change("stage1", 102, True)

    def test_existing_hostpci_is_not_overwritten(self):
        self.add_config("hostpci0: 0000:01:00.0,pcie=1\n")
        with self.assertRaisesRegex(app.Refused, "unrecognized"):
            self.host.change("stage1", 102, True)

    def test_pending_changes_are_refused(self):
        self.add_config("[PENDING]\nmemory: 6144\n")
        with self.assertRaisesRegex(app.Refused, "pending"):
            self.host.preflight(102)

    def test_unexpected_qemu_major_is_refused(self):
        self.host.version = "10.1.2-1"
        with self.assertRaisesRegex(app.Refused, "QEMU 11"):
            self.host.preflight(102)

    def test_memory_pressure_refuses_start(self):
        self.host.available = 4200
        with self.assertRaisesRegex(app.Refused, "free host RAM"):
            self.host.start(102, True)
        self.assertEqual(self.host.state, "stopped")

    def test_failed_start_records_error_and_never_adds_flags(self):
        self.host.change("stage1", 102, True)
        before = self.path().read_bytes()
        self.host.fail_start = True
        with self.assertRaisesRegex(app.Refused, "No compatibility flags"):
            self.host.start(102, True)
        self.assertEqual(before, self.path().read_bytes())
        start_log = next(p.parent / "start.log" for p in self.checkpoints()
                         if json.loads(p.read_text())["action"] == "start")
        self.assertIn("simulated", start_log.read_text())

    def test_root_placement_requires_rom_stage(self):
        self.host.change("stage1", 102, True)
        with self.assertRaisesRegex(app.Refused, "Test the N150 ROM"):
            self.host.change("root-pci", 102, True)


if __name__ == "__main__":
    unittest.main()
