import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assistant_service import answer_question, resolve_promoter
from chat_queries import find_person


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
        self.assertEqual(resolve_promoter("Enzo Villagra", promoters), "VILLAGRA ENZO")
        self.assertIsNone(resolve_promoter("desconocido", promoters))

    def test_promoter_name_order_in_questions(self):
        for name in ("Villagra Enzo", "Enzo Villagra"):
            answer, _, _ = answer_question(f"Cuántos clientes compraron {name}", self.dataset)
            self.assertIn("2 clientes de VILLAGRA ENZO", answer)

    def test_full_reordered_name_wins_over_shared_first_name(self):
        names = ["VILLAGRA ENZO", "GARCIA ENZO", "GIMENEZ JUAN MANUEL"]
        self.assertEqual(find_person("compras de Enzo Villagra", names), "VILLAGRA ENZO")
        self.assertEqual(find_person("compras de Manuel Juan Gimenez", names), "GIMENEZ JUAN MANUEL")
        self.assertIsNone(find_person("compras de Enzo", names))
        promoters = pd.DataFrame({"promotor": names[:2], "vendedor": ["61", "62"]})
        self.assertIsNone(resolve_promoter("Enzo", promoters))

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

    def test_discount_query_joins_selected_promoter_cartera(self):
        discounts = pd.DataFrame([
            {"cliente": "1", "fantasia": "Local 1", "segmento": "VALUE", "subsegmento": "LITRO", "porcentaje_total": 0.305},
            {"cliente": "2", "fantasia": "Local 2", "segmento": "VALUE", "subsegmento": "LITRO", "porcentaje_total": 0.30},
            {"cliente": "4", "fantasia": "Fuera", "segmento": "VALUE", "subsegmento": "LITRO", "porcentaje_total": 0.305},
        ])
        answer, detail, context = answer_question(
            "Qué clientes tienen 30,5% de descuento en latones 710 Value",
            self.dataset,
            fixed_promoter="VILLAGRA ENZO",
            discounts=discounts,
        )
        self.assertIn("1 clientes de VILLAGRA ENZO", answer)
        self.assertIn("no distingue un descuento exclusivo para 710 cc", answer)
        self.assertEqual(detail["Cliente"].tolist(), ["1"])
        answer, detail, context = answer_question("y de la ruta de LUJU", self.dataset, context, fixed_promoter="VILLAGRA ENZO", discounts=discounts)
        self.assertIn("1 clientes de VILLAGRA ENZO en LUJU", answer)
        answer, _, _ = answer_question("cuantos compraron core", self.dataset, context, fixed_promoter="VILLAGRA ENZO", discounts=discounts)
        self.assertIn("compraron Core", answer)

    def test_ambiguous_discount_does_not_repeat_previous_sales(self):
        _, _, context = answer_question("Cuantos clientes compraron", self.dataset, fixed_promoter="VILLAGRA ENZO")
        answer, detail, context = answer_question("5% en laton", self.dataset, context, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("¿Es descuento de CORE, VALUE LITRO o VALUE LATA?", answer)
        self.assertIsNone(detail)

    def test_red_bull_and_michelob_aliases(self):
        self.dataset["ventas"].loc[0, ["marca", "producto", "articulo_descripcion", "sku_search_text", "division"]] = [
            "RED BULL", "RED BULL CAN 250", "RED BULL CAN 250", "RED BULL CAN 250", "BEB ENERGIZANTES"
        ]
        self.dataset["ventas"].loc[1, ["marca", "producto", "articulo_descripcion", "sku_search_text"]] = [
            "MICHELOB ULTRA", "MICHELOB 710CC", "MICHELOB 710CC", "MICHELOB 710CC"
        ]
        for question in ("clientes compradores de red bull", "clientes compradores de redbull", "clientes compradores de red-bul", "clientes compradores de RB"):
            answer, detail, _ = answer_question(question, self.dataset, fixed_promoter="VILLAGRA ENZO")
            self.assertIn("1 clientes", answer)
            self.assertIn("RED BULL TODOS", answer)
            self.assertEqual(detail["Cliente"].tolist(), ["1"])
        for question in ("clientes compradores de michelob", "clientes compradores de michelob ultra"):
            answer, detail, _ = answer_question(question, self.dataset, fixed_promoter="VILLAGRA ENZO")
            self.assertIn("MICHELOB ULTRA TODOS", answer)
            self.assertEqual(detail["Cliente"].tolist(), ["2"])

    def test_chat_separates_269_from_other_calibers(self):
        sales = self.dataset["ventas"].copy()
        sales.loc[0, ["marca", "producto", "articulo_descripcion", "sku_search_text", "articulo_codigo"]] = [
            "QUILMES CLASICA", "QUILMES 269", "QUILMES CLASICA CAN 4X6 269CC", "QUILMES CLASICA CAN 4X6 269CC", "63068"
        ]
        sales.loc[1, ["marca", "producto", "articulo_descripcion", "sku_search_text", "articulo_codigo"]] = [
            "QUILMES", "QUILMES 473", "QUILMES CAN 4X6 473CC", "QUILMES CAN 4X6 473CC", "2218"
        ]
        combo = sales.iloc[[0]].copy()
        combo.loc[:, ["cliente", "cliente_nombre", "marca", "producto", "articulo_descripcion", "sku_search_text", "articulo_codigo"]] = [
            "3", "Cliente 3", "", "", "COMBO BRAH&QUIL 269 CC SUR", "COMBO BRAH&QUIL 269 CC SUR", "900473"
        ]
        self.dataset["ventas"] = pd.concat([sales, combo], ignore_index=True)
        for question, label, customers in (
            ("compradores de 269 todos", "269 TODOS", {"1", "3"}),
            ("compradores de quilmes 269", "QUILMES 269", {"1", "3"}),
            ("compradores de quilmes 473", "QUILMES 473", {"2"}),
        ):
            answer, detail, _ = answer_question(question, self.dataset, fixed_promoter="VILLAGRA ENZO")
            self.assertIn(label, answer)
            self.assertEqual(set(detail["Cliente"]), customers)

    def test_unrecognized_product_does_not_reuse_previous_one(self):
        _, _, context = answer_question("clientes compradores de redbull", self.dataset, fixed_promoter="VILLAGRA ENZO")
        answer, detail, _ = answer_question("clientes compradores de producto desconocido", self.dataset, context, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("No identifiqué el producto", answer)
        self.assertIsNone(detail)
        answer, detail, _ = answer_question("no se que poner", self.dataset, context, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("No entendí qué querés consultar", answer)
        self.assertIsNone(detail)

    def test_vague_customer_question_does_not_invent_purchase_intent(self):
        answer, detail, _ = answer_question("clientes de mi zona", self.dataset, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("No entendí qué querés consultar", answer)
        self.assertIsNone(detail)

    def test_recognized_product_implies_buyers_when_asking_for_customers(self):
        answer, detail, _ = answer_question("Cuántos clientes de Brahma tiene Enzo", self.dataset)
        self.assertIn("BRAHMA TODOS", answer)
        self.assertEqual(detail["Cliente"].tolist(), ["2"])

    def test_customer_purchase_by_code_and_fantasy_name(self):
        self.dataset["rutas_grupo"].loc[self.dataset["rutas_grupo"]["cliente"].eq("1"), ["cliente", "nombre_fantasia"]] = ["101063", "ARENAS TRAINING"]
        sales = self.dataset["ventas"]
        sales.loc[sales["cliente"].eq("1"), "cliente"] = "101063"
        sales["articulo_codigo"] = ["900399", "123"]
        sales["cantidad"] = [2, 1]
        answer, detail, context = answer_question("Compró el cliente 101063?", self.dataset, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("última compra registrada fue el 2026-10-29", answer)
        self.assertEqual(detail["SKU"].tolist(), ["900399"])
        answer, detail, context = answer_question("Cuál fue la última compra de Arenas Training", self.dataset, context, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("101063 - ARENAS TRAINING", answer)
        answer, _, _ = answer_question("Y cuál fue su última compra", self.dataset, context, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("101063 - ARENAS TRAINING", answer)

    def test_customer_without_purchase_is_limited_to_loaded_period(self):
        answer, detail, _ = answer_question("Compró el cliente 3?", self.dataset, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("No hay compras registradas", answer)
        self.assertIn("No puedo afirmar que nunca haya comprado", answer)
        self.assertIsNone(detail)

    def test_ambiguous_fantasy_name_requests_customer_code(self):
        self.dataset["rutas_grupo"].loc[self.dataset["rutas_grupo"]["cliente"].isin(["1", "2"]), "nombre_fantasia"] = "ARENAS TRAINING"
        answer, detail, _ = answer_question("Compró Arenas Training?", self.dataset, fixed_promoter="VILLAGRA ENZO")
        self.assertIn("más de un cliente", answer)
        self.assertEqual(len(detail), 2)


if __name__ == "__main__":
    unittest.main()
