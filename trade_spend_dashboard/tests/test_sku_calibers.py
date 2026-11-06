import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_queries import find_sku
from kpi_matching import sku_selection_mask


class SkuCaliberTest(unittest.TestCase):
    def setUp(self):
        self.sales = pd.DataFrame([
            ("1", "63068", "QUILMES CLASICA CAN 4X6 269CC", "QUILMES CLASICA", "269 CC LATA"),
            ("2", "2218", "QUILMES CAN 4X6 473CC", "QUILMES", "473 CC LATAS"),
            ("3", "15624", "BRAHMA CAN 4X6 269", "BRAHMA", "269 CC LATA"),
            ("4", "900473", "COMBO BRAH&QUIL 269 CC SUR", "", ""),
            ("5", "31073", "PDT TONICA CAN 4X6 269CC", "PASO DE LOS TOROS", "269 CC LATA"),
            ("6", "31434", "BRAHMA CAN 4X4 710CC", "BRAHMA", "710 CC LATAS"),
            ("7", "900490", "PROMO QUILMES 473 CC", "", ""),
        ], columns=["cliente", "articulo_codigo", "articulo_descripcion", "marca", "calibre"])
        self.sales["producto"] = self.sales["articulo_descripcion"]
        self.sales["marca_unificada"] = self.sales["marca"]
        self.sales["sku_search_text"] = self.sales["articulo_descripcion"]

    def test_269_group_and_brand_calibers(self):
        for selection, expected in (
            ("269 TODOS", {"1", "3", "4"}),
            ("QUILMES 269", {"1", "4"}),
            ("QUILMES 473", {"2", "7"}),
            ("BRAHMA 269", {"3", "4"}),
        ):
            found = set(self.sales.loc[sku_selection_mask(self.sales, [selection]), "cliente"])
            self.assertEqual(found, expected, selection)

    def test_chat_resolves_caliber_before_brand(self):
        options = ["Todos", "QUILMES TODOS", "QUILMES 1890 TODOS", "BRAHMA TODOS"]
        self.assertEqual(find_sku("compradores de 269 todos", options), "269 TODOS")
        self.assertEqual(find_sku("compradores de quilmes 269", options), "QUILMES 269")
        self.assertEqual(find_sku("compradores de qulmes 473", options), "QUILMES 473")
        self.assertEqual(find_sku("compradores de Brahma 269", options), "BRAHMA 269")


if __name__ == "__main__":
    unittest.main()
