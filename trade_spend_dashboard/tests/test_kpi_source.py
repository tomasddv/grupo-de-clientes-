import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

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

    def test_missing_current_daily_file_uses_known_current_id(self):
        files = [SimpleNamespace(path="ventadiaria octubre.txt", id="october")]
        with patch.object(kpi_source.gdown, "download_folder", return_value=files):
            self.assertEqual(kpi_source.current_daily_file_id(), kpi_source.DEFAULT_FILE_IDS["ventadiaria.txt"])

    def test_folder_listing_error_does_not_block_current_sales(self):
        with patch.object(kpi_source.gdown, "download_folder", side_effect=OSError("Drive listing unavailable")):
            self.assertEqual(kpi_source.current_daily_file_id(), kpi_source.DEFAULT_FILE_IDS["ventadiaria.txt"])

    def test_previous_month_sales_are_rejected(self):
        current = pd.Timestamp.now(tz="America/Argentina/Buenos_Aires").tz_localize(None)
        old_date = current.to_period("M").start_time - pd.Timedelta(days=1)
        with self.assertRaisesRegex(RuntimeError, "mes anterior"):
            kpi_source.validate_daily_sales_month({"fechas": [old_date]})
        kpi_source.validate_daily_sales_month({"fechas": [current]})

    def test_dataset_uses_direct_file_without_folder_listing(self):
        today = pd.Timestamp.now(tz="America/Argentina/Buenos_Aires").tz_localize(None)
        requested_ids = []

        def fake_download(*, id, output, **kwargs):
            requested_ids.append(id)
            Path(output).write_text("data", encoding="utf-8")
            return output

        kpi_source.load_kpi_dataset.clear()
        with (
            patch.dict(kpi_source.os.environ, {"KPI_DATA_DIR": ""}),
            patch.object(kpi_source.gdown, "download", side_effect=fake_download),
            patch.object(kpi_source.gdown, "download_folder", side_effect=AssertionError("listing should not run")),
            patch.object(kpi_source, "load_dataset", return_value={"fechas": [today]}),
        ):
            kpi_source.load_kpi_dataset()
        self.assertIn(kpi_source.DEFAULT_FILE_IDS["ventadiaria.txt"], requested_ids)


if __name__ == "__main__":
    unittest.main()
