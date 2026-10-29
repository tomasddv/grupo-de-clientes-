import re

import pandas as pd

from kpi_data import MICHELOB_710_COMBO_CODES, focus_sales, sin_alcohol_mask

COMBO_OPTION_PREFIX = "COMBO/PROMO: "


def non_buyer_clients(filtered: pd.DataFrame, rutas_base: pd.DataFrame, route_group: str):
    scope = rutas_base.copy()
    if route_group != "Todas":
        scope = scope[scope["grupo_ruta"].eq(route_group)]
    scope_cols = ["grupo_ruta", "ruta", "supervisor", "promotor", "vendedor", "cliente", "razon_social", "nombre_fantasia"]
    if "nombre_fantasia" not in scope.columns:
        scope["nombre_fantasia"] = ""
    scope = scope[scope_cols].drop_duplicates()
    if filtered.empty:
        result = scope.copy()
    else:
        buyers = filtered[["vendedor", "cliente"]].drop_duplicates()
        buyers["compro_foco"] = True
        result = scope.merge(buyers, on=["vendedor", "cliente"], how="left")
        result = result[result["compro_foco"].isna()].drop(columns=["compro_foco"])
    return result.sort_values(["grupo_ruta", "promotor", "ruta", "razon_social", "cliente"])


def last_day_client_activations(filtered: pd.DataFrame, target_date=None):
    if filtered.empty or "fecha" not in filtered.columns:
        return pd.DataFrame(), pd.Timestamp(target_date) if target_date is not None else None
    last_date = pd.Timestamp(target_date) if target_date is not None else pd.Timestamp(filtered["fecha"].dropna().max())
    if pd.isna(last_date):
        return pd.DataFrame(), None
    previous_clients = set(
        filtered.loc[filtered["fecha"].lt(last_date), "cliente"].dropna().unique()
    )
    current = filtered[
        filtered["fecha"].eq(last_date)
        & ~filtered["cliente"].isin(previous_clients)
    ].copy()
    if current.empty:
        return current.iloc[0:0].copy(), last_date
    for col in ["producto", "articulo_descripcion", "marca", "division"]:
        if col not in current.columns:
            current[col] = ""
    group_cols = [
        col
        for col in [
            "grupo_ruta",
            "ruta",
            "supervisor",
            "promotor",
            "vendedor",
            "cliente",
            "cliente_nombre",
        ]
        if col in current.columns
    ]
    activation = (
        current.groupby(group_cols, as_index=False)
        .agg(
            productos=("producto", lambda s: ", ".join(sorted(set(x for x in s.fillna("").astype(str) if x))) or "Combo"),
            articulos=("articulo_descripcion", lambda s: ", ".join(sorted(set(x for x in s.fillna("").astype(str) if x)))[:240]),
            marcas=("marca", lambda s: ", ".join(sorted(set(x for x in s.fillna("").astype(str) if x))) or "Combo"),
            skus=("producto", "nunique"),
        )
    )
    sort_cols = [
        col
        for col in ["grupo_ruta", "promotor", "ruta", "cliente"]
        if col in activation.columns
    ]
    if sort_cols:
        activation = activation.sort_values(sort_cols)
    return activation, last_date


def filter_sales_by_focus_purchase_range(
    ventas_df: pd.DataFrame,
    start_date,
    end_date,
    focus: str,
    rutas_base: pd.DataFrame | None = None,
    route: str = "Todas",
):
    filtered = focus_sales(ventas_df, focus)
    filtered = filtered[(filtered["fecha"].ge(pd.Timestamp(start_date))) & (filtered["fecha"].le(pd.Timestamp(end_date)))]
    if rutas_base is not None and rutas_base.empty:
        return filtered.iloc[0:0].copy()
    if rutas_base is not None and not rutas_base.empty:
        route_scope = rutas_base.copy()
        if route != "Todas":
            route_scope = route_scope[route_scope["grupo_ruta"].eq(route)]
        route_cols = [
            col
            for col in ["grupo_ruta", "ruta", "supervisor", "promotor", "vendedor", "cliente"]
            if col in route_scope.columns
        ]
        route_keys = route_scope[route_cols].drop_duplicates()
        sales_without_route_owner = filtered.drop(
            columns=[
                col
                for col in ["grupo_ruta", "ruta", "supervisor", "promotor", "vendedor"]
                if col in filtered.columns
            ],
            errors="ignore",
        )
        filtered = route_keys.merge(sales_without_route_owner, on="cliente", how="inner")
    return filtered


def filter_business_sku_purchase_range(
    ventas_df: pd.DataFrame,
    start_date,
    end_date,
    business: str,
    skus,
    rutas_base: pd.DataFrame | None = None,
    route: str = "Todas",
):
    filtered = ventas_df[(ventas_df["fecha"].ge(pd.Timestamp(start_date))) & (ventas_df["fecha"].le(pd.Timestamp(end_date)))].copy()
    if isinstance(skus, str):
        selected_skus = [skus]
    else:
        selected_skus = list(skus or [])
    selected_skus = [sku for sku in selected_skus if sku and sku != "Todos"]
    if selected_skus:
        filtered = filtered[sku_selection_mask(filtered, selected_skus)]
    elif business != "Todos":
        filtered = filtered[business_mask(filtered, business)]
    if rutas_base is not None and rutas_base.empty:
        return filtered.iloc[0:0].copy()
    if rutas_base is not None and not rutas_base.empty:
        route_scope = rutas_base.copy()
        if route != "Todas":
            route_scope = route_scope[route_scope["grupo_ruta"].eq(route)]
        route_cols = [
            col
            for col in ["grupo_ruta", "ruta", "supervisor", "promotor", "vendedor", "cliente"]
            if col in route_scope.columns
        ]
        route_keys = route_scope[route_cols].drop_duplicates()
        sales_without_route_owner = filtered.drop(
            columns=[
                col
                for col in ["grupo_ruta", "ruta", "supervisor", "promotor", "vendedor"]
                if col in filtered.columns
            ],
            errors="ignore",
        )
        filtered = route_keys.merge(sales_without_route_owner, on="cliente", how="inner")
    return filtered


def sku_options_for_business(ventas_df: pd.DataFrame, business: str):
    scoped = ventas_df.copy()
    if business != "Todos":
        scoped = scoped[business_mask(scoped, business)]
    scoped["_marca_option"] = scoped["marca"].fillna("").str.upper()
    scoped["_producto_option"] = scoped["producto"].fillna("")
    values = []
    for brand_value in sorted(value for value in scoped["_marca_option"].unique() if value):
        values.append(f"{brand_value} TODOS")
        brand_products = sorted(
            value
            for value in scoped.loc[scoped["_marca_option"].eq(brand_value), "_producto_option"].unique()
            if value
        )
        values.extend(brand_products)
    unbranded_products = sorted(
        value
        for value in scoped.loc[scoped["_marca_option"].eq(""), "_producto_option"].unique()
        if value
    )
    values.extend(unbranded_products)
    search_text = scoped.get("sku_search_text", pd.Series("", index=scoped.index)).fillna("").str.upper()
    special_options = []
    if search_text.str.contains("PURE GOLD| SA PG |P GOLD|PORRON PURE GOLD", regex=True, na=False).any():
        special_options.extend(["PURE GOLD 330/PORRON", "PURE GOLD 473 LATA", "PURE GOLD TODOS"])
    if search_text.str.contains("GATORADE|\\bGATO\\b|\\bGAT\\b|\\bGTD\\b", regex=True, na=False).any():
        special_options.append("GATORADE TODOS")
    if search_text.str.contains("PEPSI.*BLACK|PEP BLACK|PEP BL|BLACK 2\\.?500|COMBO BLACK", regex=True, na=False).any():
        special_options.append("PEPSI BLACK TODOS")
    if sin_alcohol_mask(scoped).any():
        special_options.append("SIN ALCOHOL TODOS")
    special_options.extend(dynamic_combo_promo_options(ventas_df if business != "Todos" else scoped))
    values = list(dict.fromkeys(special_options + values))
    return ["Todos"] + values


def combo_promo_marker_mask(search_text: pd.Series):
    return search_text.str.contains("\\bCOMBO\\b|\\bPROMO\\b", regex=True, na=False)


def combo_option_label(description: str):
    return f"{COMBO_OPTION_PREFIX}{str(description).strip()}"


def dynamic_combo_promo_options(ventas_df: pd.DataFrame):
    if ventas_df.empty or "articulo_descripcion" not in ventas_df.columns:
        return []
    search_text = ventas_df.get("sku_search_text", pd.Series("", index=ventas_df.index)).fillna("").str.upper()
    combo_rows = ventas_df[combo_promo_marker_mask(search_text)].copy()
    if combo_rows.empty:
        return []
    descriptions = (
        combo_rows["articulo_descripcion"]
        .fillna("")
        .astype(str)
        .str.strip()
        .loc[lambda s: s.ne("")]
        .drop_duplicates()
        .sort_values()
    )
    return [combo_option_label(desc) for desc in descriptions]


def selected_combo_descriptions(selected_skus: list[str]):
    descriptions = []
    for sku in selected_skus:
        value = str(sku).strip()
        if value.upper().startswith(COMBO_OPTION_PREFIX):
            descriptions.append(value[len(COMBO_OPTION_PREFIX):].strip())
    return descriptions


def sku_selection_mask(ventas_df: pd.DataFrame, selected_skus: list[str]):
    product = ventas_df["producto"].fillna("")
    brand = ventas_df["marca"].fillna("").str.upper()
    unified_brand = ventas_df.get("marca_unificada", pd.Series("", index=ventas_df.index)).fillna("").str.upper()
    search_text = ventas_df.get("sku_search_text", pd.Series("", index=ventas_df.index)).fillna("").str.upper()
    selected_upper = {str(sku).upper() for sku in selected_skus}
    virtual_prefixes = ("PURE GOLD", "GATORADE", "PEPSI BLACK", "SIN ALCOHOL")
    combo_descriptions = selected_combo_descriptions(selected_skus)
    combo_option_prefix_upper = COMBO_OPTION_PREFIX.upper()
    selected_upper_without_combos = {sku for sku in selected_upper if not sku.startswith(combo_option_prefix_upper)}
    brand_all_selections = {
        sku[:-6].strip()
        for sku in selected_upper_without_combos
        if sku.endswith(" TODOS") and not sku.startswith(virtual_prefixes)
    }
    direct_skus = [
        sku
        for sku in selected_skus
        if not str(sku).upper().startswith(virtual_prefixes)
        and not str(sku).upper().endswith(" TODOS")
        and not str(sku).upper().startswith(COMBO_OPTION_PREFIX)
    ]
    mask = product.isin(direct_skus)
    if combo_descriptions:
        description = ventas_df.get("articulo_descripcion", pd.Series("", index=ventas_df.index)).fillna("").astype(str).str.strip()
        mask = mask | description.isin(combo_descriptions)
    if brand_all_selections:
        mask = mask | brand.isin(brand_all_selections) | unified_brand.isin(brand_all_selections)
        water_combo = water_combo_mask(search_text)
        if any("ECO" in brand_name for brand_name in brand_all_selections):
            mask = mask | (water_combo & search_text.str.contains("ECO", regex=True, na=False))
        if any("NESTLE" in brand_name or "PUREZA" in brand_name for brand_name in brand_all_selections):
            mask = mask | (water_combo & search_text.str.contains("NESTLE|NPV|PUREZA", regex=True, na=False))
        if "GLACIAR" in brand_all_selections:
            mask = mask | (water_combo & search_text.str.contains("GLACIAR", regex=True, na=False))
        brand_combo_aliases = {
            "BRAHMA": r"BRAHMA|\bBR\b",
            "QUILMES": r"QUILMES|\bQC\b",
            "BUDWEISER": r"BUD|BUDWEISER",
            "PATAGONIA": r"PATAGONIA|\bPAT\b",
            "MICHELOB ULTRA": r"MICHELOB",
            "STELLA ARTOIS": r"STELLA",
            "CORONA": r"CORONA",
            "ANDES ORIGEN": r"ANDES",
        }
        beer_combo = beer_combo_mask(search_text)
        for brand_name, pattern in brand_combo_aliases.items():
            if brand_name in brand_all_selections:
                mask = mask | (beer_combo & search_text.str.contains(pattern, regex=True, na=False))
        nabs_combo_aliases = {
            "PEPSI": r"\bPEPSI\b",
            "MIRINDA": r"MIRINDA",
            "7UP": r"\b7UP\b",
            "RED BULL": r"RED\s*BULL|REDBULL|\bRB\b",
            "GATORADE": r"GATORADE|\bGTD\b",
        }
        nabs_combo = nabs_combo_mask(search_text)
        for brand_name, pattern in nabs_combo_aliases.items():
            if brand_name in brand_all_selections:
                mask = mask | (nabs_combo & search_text.str.contains(pattern, regex=True, na=False))

    def is_pepsi_black_alias(value: str):
        return bool(re.search(r"PEPSI.*BLACK|PEP BLACK|PEP BL|BLACK 2\.?500", value))

    selected_rows = ventas_df[product.isin(direct_skus)]
    selected_brands = set(selected_rows.get("marca", pd.Series(dtype=str)).fillna("").str.upper())
    if selected_rows.get("articulo_codigo", pd.Series(dtype=str)).isin({"49827"}).any():
        mask = mask | ventas_df["articulo_codigo"].isin(MICHELOB_710_COMBO_CODES)
    gatorade_selected = (
        "GATORADE TODOS" in selected_upper_without_combos
        or "GATORADE" in selected_brands
        or any("GATORADE" in sku or "GATO" in sku or re.search(r"\bGAT\b|\bGT\b", sku) for sku in selected_upper_without_combos)
    )
    pepsi_black_selected = (
        "PEPSI BLACK TODOS" in selected_upper_without_combos
        or "PEPSI BLACK" in selected_brands
        or any(re.search(r"PEPSI.*BLACK|PEP BLACK|PEP BL|BLACK 2\.?500", sku) for sku in selected_upper_without_combos)
    )
    latones_selected = any(re.search(r"LATON|LATONES|\b710\b|L710", sku) for sku in selected_upper_without_combos)
    for sku in selected_upper_without_combos:
        if sku.startswith(virtual_prefixes):
            continue
        if is_pepsi_black_alias(sku):
            continue
        sku_tokens = [token for token in re.findall(r"[A-Z0-9]+", sku) if len(token) >= 3]
        meaningful_tokens = [
            token for token in sku_tokens
            if token not in {"X6", "X12", "X24", "4X6", "4X4", "2024", "IMP", "CAR", "BOT", "PET", "VIDRIO", "LATAS", "LATA", "CC"}
        ]
        if sku:
            mask = mask | search_text.str.contains(re.escape(sku), regex=True, na=False)
        if len(meaningful_tokens) >= 2:
            token_hits = pd.Series(True, index=ventas_df.index)
            for token in meaningful_tokens[:4]:
                token_hits = token_hits & search_text.str.contains(re.escape(token), regex=True, na=False)
            mask = mask | token_hits

    gatorade_base = search_text.str.contains("GATORADE|\\bGATO\\b|\\bGAT\\b|\\bGTD\\b|COMBO GTD", regex=True, na=False)
    if gatorade_selected:
        mask = mask | gatorade_base

    pepsi_black_base = search_text.str.contains(
        "PEPSI.*BLACK|PEP BLACK|PEP BL|BLACK 2\\.?500|COMBO BLACK",
        regex=True,
        na=False,
    )
    if pepsi_black_selected:
        mask = mask | pepsi_black_base

    if "SIN ALCOHOL TODOS" in selected_upper_without_combos:
        mask = mask | sin_alcohol_mask(ventas_df)

    if latones_selected:
        mask = mask | latones_combo_mask(search_text)

    pure_gold_base = search_text.str.contains("PURE GOLD| SA PG |P GOLD", regex=True, na=False)
    if "PURE GOLD TODOS" in selected_upper_without_combos:
        mask = mask | pure_gold_base
    if "PURE GOLD 330/PORRON" in selected_upper_without_combos:
        mask = mask | (
            pure_gold_base
            & search_text.str.contains("330|B330|PORRON|SIXPACK", regex=True, na=False)
        )
    if "PURE GOLD 473 LATA" in selected_upper_without_combos:
        mask = mask | (
            pure_gold_base
            & search_text.str.contains("473|L473|LATA|LATAS|CAN", regex=True, na=False)
        )
    for sku in selected_upper_without_combos:
        if "PG" in sku or "P GOLD" in sku or "PURE GOLD" in sku:
            if "330" in sku or "B330" in sku or "PORRON" in sku:
                mask = mask | (
                    pure_gold_base
                    & search_text.str.contains("330|B330|PORRON|SIXPACK", regex=True, na=False)
                )
            if "473" in sku or "L473" in sku or "LATA" in sku:
                mask = mask | (
                    pure_gold_base
                    & search_text.str.contains("473|L473|LATA|LATAS|CAN", regex=True, na=False)
                )
    return mask


def water_combo_mask(search_text: pd.Series):
    return (
        search_text.str.contains("\\bCOMBO\\b|\\bPROMO\\b", regex=True, na=False)
        & search_text.str.contains("BIDON|NESTLE|PUREZA|NPV|ECO|GLACIAR|AGUA", regex=True, na=False)
    )


def beer_combo_mask(search_text: pd.Series):
    return (
        search_text.str.contains("\\bCOMBO\\b|\\bPROMO\\b", regex=True, na=False)
        & search_text.str.contains(
            r"LATON|LATONES|\b710\b|L710|SA 710|LATA|LATAS|CERVEZA|PATAGONIA|\bPAT\b|"
            r"MICHELOB|PURE GOLD|\b0\.0\b|BRAHMA|QUILMES|BUD|CORONA|STELLA|ANDES|QC|BR",
            regex=True,
            na=False,
        )
    )


def latones_combo_mask(search_text: pd.Series):
    return (
        search_text.str.contains("\\bCOMBO\\b|\\bPROMO\\b", regex=True, na=False)
        & search_text.str.contains(r"LATON|LATONES|\b710\b|L710|SA 710|710 OW", regex=True, na=False)
    )


def nabs_combo_mask(search_text: pd.Series):
    return (
        search_text.str.contains("\\bCOMBO\\b|\\bPROMO\\b", regex=True, na=False)
        & search_text.str.contains(
            r"PEPSI|\bBLACK\b|MIRINDA|\b7UP\b|GATORADE|\bGTD\b|RED\s*BULL|REDBULL|\bRB\b|SABORIZADAS|ENERGIA|ENERGÍA",
            regex=True,
            na=False,
        )
    )


def spirits_combo_mask(search_text: pd.Series):
    return (
        search_text.str.contains("\\bCOMBO\\b|\\bPROMO\\b", regex=True, na=False)
        & search_text.str.contains(r"\bGIN\b|SPIRITS", regex=True, na=False)
    )


def business_mask(ventas_df: pd.DataFrame, business: str):
    division = ventas_df["division"].fillna("").str.upper()
    unidad = ventas_df["unidad_negocio"].fillna("").str.upper() if "unidad_negocio" in ventas_df.columns else ""
    search_text = ventas_df.get("sku_search_text", pd.Series("", index=ventas_df.index)).fillna("").str.upper()
    if business == "CZA":
        return division.isin(["CERVEZAS", "ENV CERVEZAS"]) | beer_combo_mask(search_text)
    if business == "UNG":
        return division.isin(["GASEOSAS", "BEBIDAS SABORIZADAS", "ISOTONICAS", "BEB ENERGIZANTES"]) | nabs_combo_mask(search_text)
    if business == "AGUAS":
        return division.eq("AGUAS") | water_combo_mask(search_text)
    if business == "MKTP":
        return division.str.contains("MKTPLACE|MARKETPLACE", na=False) | pd.Series(unidad, index=ventas_df.index).str.contains("MARKETPLACE", na=False)
    if business == "SPIRITS":
        return division.str.contains("SPIRITS", na=False) | spirits_combo_mask(search_text)
    if business == "OTROS":
        known = (
            division.isin(["CERVEZAS", "ENV CERVEZAS", "GASEOSAS", "BEBIDAS SABORIZADAS", "ISOTONICAS", "BEB ENERGIZANTES", "AGUAS"])
            | division.str.contains("MKTPLACE|MARKETPLACE|SPIRITS", na=False)
            | pd.Series(unidad, index=ventas_df.index).str.contains("MARKETPLACE", na=False)
        )
        return ~known
    return pd.Series(True, index=ventas_df.index)
