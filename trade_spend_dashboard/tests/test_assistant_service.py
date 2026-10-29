import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assistant_service import answer_question, resolve_promoter


class AssistantServiceTest(unittest.TestCase):
    def setUp(self):
        routes = pd.DataFrame([
            {"grupo_ruta": "LUJU", "ruta": "611", "supervisor": "ISMAEL BRUNO", "promotor": "VILLAGRA ENZO", "vendedor": "61", "cliente": str(code), "razon_social": f"Cliente {code}", "nombre_fantasia": f"Local {code}"}
            for code in (1, 2, 3)
        ])
        sales = pd.DataFrame([
            {"fecha": pd.Timestamp("2026-10-29"), "cliente": "1", "cliente_nombre": "Cliente 1", "vendedor": "61", "marca": "QUILMES 1890", "division": "CERVEZAS", "producto": "QUILMES 1890 1L", "articulo_descripcion": "QUILMES 1890 1L", "sku_search_text": "QUILMES 1890 1L"},
            {"fecha": pd.Timestamp("2026-10-29"), "cliente": "2", "cliente_nombre": "Cliente 2", "vendedor": "61", "marca": "BRAHMA", "division": "CERVEZAS", "producto": "BRAHMA 1L", "articulo_descripcion": "BRAHMA 1L", "sku_search_text": "BRAHMA 1L"},
        ])
        self.dataset = {
            "ventas": sales,
            "rutas_grupo": routes,
            "promotores": routes[["vendedor", "promotor", "supervisor"]].drop_duplicates(),
            "fechas": [pd.Timestamp("2026-10-29")],
        }

    def test_focus_and_non_buyers_keep_promoter_context(self):
        context = None
        answer, _, context = answer_question("Cuantos clientes compraron Enzo", self.dataset, context)
        self.assertIn("2 clientes de VILLAGRA ENZO", answer)
        answer, routes, context = answer_question("De que ruta es", self.dataset, context)
        self.assertIn("VILLAGRA ENZO", answer)
        self.assertEqual(routes["ruta"].tolist(), ["611"])
        answer, _, context = answer_question("Y de Value", self.dataset, context)
        self.assertIn("1 clientes de VILLAGRA ENZO compraron Value", answer)
        answer, missing, context = answer_question("Que clientes no compraron", self.dataset, context)
        self.assertIn("2 clientes", answer)
        self.assertEqual(set(missing["cliente"]), {"2", "3"})
        answer, _, _ = answer_question("De la ruta de LUJU", self.dataset, context)
        self.assertIn("VILLAGRA ENZO en LUJU", answer)

    def test_resolve_promoter_by_name_or_vendor_code(self):
        promoters = self.dataset["promotores"]
        self.assertEqual(resolve_promoter("61", promoters), "VILLAGRA ENZO")
        self.assertEqual(resolve_promoter("villagra enzo", promoters), "VILLAGRA ENZO")
        self.assertIsNone(resolve_promoter("desconocido", promoters))

    def test_fixed_promoter_cannot_be_changed_by_question(self):
        other = pd.DataFrame([{"vendedor": "99", "promotor": "NICASTRO LUCAS", "supervisor": "OTRO"}])
        self.dataset["promotores"] = pd.concat([self.dataset["promotores"], other], ignore_index=True)
        self.dataset["rutas_grupo"] = pd.concat([
            self.dataset["rutas_grupo"],
            pd.DataFrame([{"grupo_ruta": "MISA", "ruta": "991", "supervisor": "OTRO", "promotor": "NICASTRO LUCAS", "vendedor": "99", "cliente": "4", "razon_social": "Cliente 4", "nombre_fantasia": "Local 4"}]),
        ], ignore_index=True)
        answer, _, context = answer_question("Cuantos clientes tiene Nicastro Lucas", self.dataset, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("VILLAGRA ENZO", answer)
        self.assertEqual(context["promoter"], "VILLAGRA ENZO")


if __name__ == "__main__":
    unittest.main()
