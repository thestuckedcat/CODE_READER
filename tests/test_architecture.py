"""Architecture, runtime isolation, and documentation contract tests."""
import ast
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ArchitectureTest(unittest.TestCase):
    def test_domain_has_no_outward_dependencies(self):
        for source in (ROOT / "scripts" / "atlas" / "domain").glob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertFalse(any("infrastructure" in name or "application" in name or "interfaces" in name for name in imports))

    def test_application_boundary_and_compatibility_facade(self):
        from atlas.application import AtlasApplication
        from atlas.core import Store
        from atlas.infrastructure.store import Store as LayeredStore

        self.assertIs(Store, LayeredStore)
        self.assertTrue(AtlasApplication().workflow())

    def test_runtime_isolation(self):
        before = os.environ.get("PATH", "")
        from setup_runtime import platform_key

        path = ROOT / "runtime" / platform_key() / "venv"
        self.assertTrue(str(path.resolve()).startswith(str(ROOT.resolve())))
        self.assertEqual(before, os.environ.get("PATH", ""), "importing setup helpers must not mutate PATH")

    def test_document_reconciliation(self):
        from check_docs import check

        self.assertEqual(check(ROOT), [])


if __name__ == "__main__":
    unittest.main()
