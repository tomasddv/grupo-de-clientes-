from __future__ import annotations

import re

import pandas as pd

from chat_queries import asks_for_unsupported_period, classify_question, find_focus, find_named_entity, find_person, find_sku, is_route_question
from chat_queries import normalize_text
from kpi_matching import filter_business_sku_purchase_range, filter_sales_by_focus_purchase_range, last_day_client_activations, non_buyer_clients, sku_options_for_business


def resolve_promoter(identity: str, promoters: pd.DataFrame) -> str | None:
    key = normalize_text(identity)
    if not key:
        return None
    matches = promoters[
        promoters["promotor"].map(normalize_text).eq(key)
        | promoters["vendedor"].astype(str).map(normalize_text).eq(key)
    ]["promotor"].dropna().unique()
    return str(matches[0]) if len(matches) == 1 else None


def discount_request(question: str, context: dict, route_followup: bool = False) -> tuple[float, str, str] | None:
    normalized = normalize_text(question)
    if re.search(r"\b(compr\w*|venta\w*|vend\w*|activ\w*)\b", normalized) and "descuento" not in normalized:
        return None
    if not ("descuento" in normalized or "%" in question or route_followup or re.search(r"\b(value|core|laton\w*|litro|lata)\b", normalized)):
        return None
    match = re.search(r"(?<!\d)(\d{1,2}(?:[,.]\d{1,2})?)\s*%?(?!\d)", normalized)
    if match and ("descuento" in normalized or "%" in question):
        context["discount_pct"] = float(match.group(1).replace(",", "."))
    if "value" in normalized:
        context["discount_segment"] = "VALUE"
        if "lata" in normalized and "laton" not in normalized:
            context["discount_subsegment"] = "LATA"
        elif re.search(r"\b(litro|laton|710)\b", normalized):
            context["discount_subsegment"] = "LITRO"
    elif "core" in normalized:
        context["discount_segment"] = "CORE"
        context["discount_subsegment"] = "CORE"
    if "discount_pct" not in context or "discount_segment" not in context:
        return None
    return context["discount_pct"], context["discount_segment"], context.get("discount_subsegment", "")


def discount_answer(request: tuple[float, str, str], discounts: pd.DataFrame, scope: pd.DataFrame, owner: str, question: str):
    percentage, segment, subsegment = request
    if segment == "VALUE" and not subsegment:
        return "¿Buscás el descuento de VALUE LITRO o VALUE LATA?", None
    if discounts is None or discounts.empty:
        return "No tengo cargada la tabla de descuentos para responder esta consulta.", None
    rows = discounts.copy()
    rows["cliente"] = rows["cliente"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    rows["porcentaje_total"] = pd.to_numeric(rows["porcentaje_total"], errors="coerce")
    rows = rows[
        rows["segmento"].astype(str).str.upper().eq(segment)
        & rows["subsegmento"].astype(str).str.upper().eq(subsegment)
        & rows["porcentaje_total"].sub(percentage / 100).abs().lt(0.00001)
    ]
    cartera = scope[["cliente", "promotor", "grupo_ruta"]].drop_duplicates("cliente").rename(columns={"promotor": "promotor_cartera"}).copy()
    cartera["cliente"] = cartera["cliente"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    detail = rows.merge(cartera, on="cliente", how="inner", suffixes=("", "_cartera"))
    detail = detail[["cliente", "fantasia", "promotor_cartera", "grupo_ruta", "porcentaje_total"]].drop_duplicates("cliente")
    detail = detail.rename(columns={"cliente": "Cliente", "fantasia": "Nombre fantasía", "promotor_cartera": "Promotor", "grupo_ruta": "Grupo ruta", "porcentaje_total": "Descuento"})
    detail["Descuento"] = detail["Descuento"].map(lambda value: f"{value * 100:.2f}%")
    label = f"{segment} {subsegment}".strip()
    note = " La fuente no distingue un descuento exclusivo para 710 cc." if re.search(r"\b710\b", normalize_text(question)) else ""
    return f"{len(detail):,} clientes de {owner} tienen {percentage:g}% de descuento en {label}.{note}", detail


def answer_question(question: str, dataset: dict, previous: dict | None = None, fixed_promoter: str | None = None, discounts: pd.DataFrame | None = None):
    context = dict(previous or {})
    sales = dataset["ventas"]
    routes = dataset["rutas_grupo"]
    promoters = dataset["promotores"]
    end = pd.Timestamp(max(dataset["fechas"]))
    start = end.replace(day=1)

    found_promoter = None if fixed_promoter else find_person(question, promoters["promotor"].dropna().unique())
    found_supervisor = None if fixed_promoter or found_promoter else find_person(question, promoters["supervisor"].dropna().unique())
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
    if fixed_promoter:
        context["promoter"] = fixed_promoter
        context.pop("supervisor", None)

    intent = found_intent or (context.get("intent") if found_route or found_sku or found_focus else None)
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

    discount_signal = "descuento" in normalize_text(question) or "%" in question
    discount = discount_request(question, context, route_followup=bool(found_route and "discount_pct" in context))
    if discount:
        answer, detail = discount_answer(discount, discounts, scope, owner, question)
        return answer, detail, context
    if discount_signal:
        if "discount_pct" not in context:
            return "¿Qué porcentaje de descuento querés consultar?", None, context
        return "¿Es descuento de CORE, VALUE LITRO o VALUE LATA? No puedo atribuir un descuento exclusivo al calibre 710 cc.", None, context

    if asks_for_unsupported_period(question, end.month):
        return "Por ahora puedo consultar el mes de la venta diaria; los cierres anteriores están en el tablero de KPIs.", None, context
    if intent is None:
        return "No entendí qué querés consultar. Podés preguntarme por compras de un producto, clientes no compradores o un porcentaje de descuento de CORE, VALUE LITRO o VALUE LATA.", None, context
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
