from __future__ import annotations

import re

import pandas as pd

from chat_queries import asks_for_unsupported_period, classify_question, find_focus, find_named_entity, find_person, find_sku, is_route_question
from kpi_matching import filter_business_sku_purchase_range, filter_sales_by_focus_purchase_range, last_day_client_activations, non_buyer_clients, sku_options_for_business


def answer_question(question: str, dataset: dict, previous: dict | None = None):
    context = dict(previous or {})
    sales = dataset["ventas"]
    routes = dataset["rutas_grupo"]
    promoters = dataset["promotores"]
    end = pd.Timestamp(max(dataset["fechas"]))
    start = end.replace(day=1)

    found_promoter = find_person(question, promoters["promotor"].dropna().unique())
    found_supervisor = find_person(question, promoters["supervisor"].dropna().unique()) if found_promoter is None else None
    found_route = find_named_entity(question, routes["grupo_ruta"].dropna().unique())
    found_focus = find_focus(question)
    found_sku = None if found_focus else find_sku(question, sku_options_for_business(sales, "Todos"))
    found_intent = "route" if is_route_question(question) else classify_question(question)

    if found_promoter and found_promoter != context.get("promoter"):
        context.pop("route", None)
        context.pop("supervisor", None)
    if found_supervisor and found_supervisor != context.get("supervisor"):
        context.pop("promoter", None)
        context.pop("route", None)
    if found_promoter:
        context["promoter"] = found_promoter
    if found_supervisor:
        context["supervisor"] = found_supervisor
    if found_route:
        context["route"] = found_route
    if found_focus:
        context["focus"] = found_focus
        context.pop("sku", None)
    if found_sku:
        context["sku"] = found_sku
        context.pop("focus", None)
    if found_intent and found_intent != "route":
        context["intent"] = found_intent

    intent = found_intent or context.get("intent") or ("buyers" if found_sku or found_focus else None)
    promoter = context.get("promoter")
    supervisor = context.get("supervisor")
    route = context.get("route")
    scope = routes
    if supervisor:
        scope = scope[scope["supervisor"].eq(supervisor)]
    if promoter:
        scope = scope[scope["promotor"].eq(promoter)]
    if route:
        scope = scope[scope["grupo_ruta"].eq(route)]
    owner = promoter or supervisor or "todas las rutas"
    if route:
        owner += f" en {route}"

    if asks_for_unsupported_period(question, end.month):
        return "Por ahora puedo consultar el mes de la venta diaria; los cierres anteriores están en el tablero de KPIs.", None, context
    if intent is None:
        return "Preguntame, por ejemplo: «¿Cuántos clientes de Pure Gold tiene Nicastro Lucas?». También puedo listar no compradores, rutas y activaciones del último día.", None, context
    if intent == "route":
        if not promoter and not supervisor:
            return "¿De qué promotor o supervisor querés saber las rutas?", None, context
        route_detail = scope[["grupo_ruta", "ruta", "promotor", "supervisor"]].drop_duplicates().sort_values(["grupo_ruta", "ruta"])
        return f"{owner} tiene {route_detail['ruta'].nunique():,} rutas en la cartera cargada.", route_detail, context
    if not found_sku and not found_focus and not context.get("sku") and not context.get("focus") and re.search(r"\bclientes\s+de\s+.+?\s+tiene\b", question, flags=re.IGNORECASE):
        return "No identifiqué el producto. Escribí la marca o variedad como figura en el tablero.", None, context

    focus = context.get("focus")
    sku = context.get("sku")
    if focus:
        filtered = filter_sales_by_focus_purchase_range(sales, start, end, focus, scope)
    else:
        filtered = filter_business_sku_purchase_range(sales, start, end, "Todos", [sku] if sku else ["Todos"], scope)
    product = focus or sku or "cualquier producto"
    period = f"del {start.date()} al {end.date()}"
    if intent == "non_buyers":
        detail = non_buyer_clients(filtered, scope, "Todas")
        detail = detail[["cliente", "razon_social", "nombre_fantasia", "promotor", "supervisor", "grupo_ruta"]].drop_duplicates()
        return f"{len(detail):,} clientes de {owner} no compraron {product} {period}.", detail, context
    if intent == "last_activations":
        activated, _ = last_day_client_activations(filtered, end)
        detail = activated[["cliente", "cliente_nombre", "promotor", "fecha"]].drop_duplicates("cliente") if not activated.empty else None
        count = 0 if detail is None else len(detail)
        return f"{count:,} clientes de {owner} compraron {product} por primera vez en el mes el {end.date()}.", detail, context
    detail = filtered.groupby("cliente", as_index=False).agg(
        **{"Razón Social": ("cliente_nombre", "first"), "Primera compra": ("fecha", "min"), "Última compra": ("fecha", "max")}
    ).rename(columns={"cliente": "Cliente"})
    return f"{len(detail):,} clientes de {owner} compraron {product} {period}.", detail, context
