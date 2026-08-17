from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import data


class NoProductionDataBootstrapTests(unittest.TestCase):
    def test_no_snapshot_returns_an_empty_selector_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(data, "PROJECT_ROOT", root), patch.object(data, "SNAPSHOTS_ROOT", root / "data" / "snapshots"):
                self.assertEqual(data.snapshot_options(), [])
