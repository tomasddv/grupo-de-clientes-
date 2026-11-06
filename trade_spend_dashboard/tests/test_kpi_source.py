import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kpi_source


class KpiSourceTest(unittest.TestCase):
    def test_current_daily_file_is_found_by_exact_name(self):
        files = [
            SimpleNamespace(path="ventadiaria octubre.txt", id="october"),
            SimpleNamespace(path="ventadiaria bultos.txt", id="bultos"),
            SimpleNamespace(path="ventadiaria.txt", id="november"),
        ]
        with patch.object(kpi_source.gdown, "download_folder", return_value=files):
            self.assertEqual(kpi_source.current_daily_file_id(), "november")

    def test_missing_current_daily_file_fails_instead_of_using_october(self):
        files = [SimpleNamespace(path="ventadiaria octubre.txt", id="october")]
        with patch.object(kpi_source.gdown, "download_folder", return_value=files):
            with self.assertRaisesRegex(RuntimeError, "ventadiaria.txt"):
                kpi_source.current_daily_file_id()


if __name__ == "__main__":
    unittest.main()
