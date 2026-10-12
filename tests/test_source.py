import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_source", ROOT / "scripts/prepare-igd-source.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class SourceTests(unittest.TestCase):
    def test_extract_and_patch_fresh_tree(self):
        scratch = ROOT / "build/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            tree = Path(temporary)
            source.prepare(tree, ROOT)
            driver = (tree / "OvmfPkg/IgdAssignmentDxe/IgdAssignment.c").read_text()
            self.assertIn("Copyright (C) 2018, Red Hat, Inc.", driver)
            self.assertIn("DeviceId == 0x46D4", driver)
            self.assertIn("N150 ? 0xC0 : ASSIGNED_IGD_PCI_BDSM_OFFSET", driver)
            self.assertIn("N150 ? 2 : 1", driver)
            self.assertIn("if (!IsN150 (PciIo)", driver)
            self.assertTrue((tree / "IntelIgdInit.dsc").is_file())


if __name__ == "__main__":
    unittest.main()
