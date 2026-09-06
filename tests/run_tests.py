"""Run behavioral integration tests from either source or portable distribution."""
import unittest
from pathlib import Path
suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_*.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
