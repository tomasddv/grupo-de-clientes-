import re
import unicodedata


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value).casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", normalized).strip()


def classify_question(question: str) -> str | None:
    normalized = normalize_text(question)
    if not normalized:
        return None
    if re.search(r"\b(no compr|sin compr|faltan|restan|pendientes)\w*", normalized):
        return "non_buyers"
    if re.search(r"\b(activ|nuevos)\w*", normalized) and re.search(r"\b(hoy|ultimo dia|ayer)\b", normalized):
        return "last_activations"
    if re.search(r"\b(compr|venta|vend|activ)\w*", normalized):
        return "buyers"
    return None


def find_named_entity(question: str, names) -> str | None:
    normalized = normalize_text(question)
    matches = [name for name in names if normalize_text(name) and re.search(r"(?<!\w)" + re.escape(normalize_text(name)) + r"(?!\w)", normalized)]
    return max(matches, key=lambda name: len(normalize_text(name)), default=None)


def find_person(question: str, names) -> str | None:
    exact = find_named_entity(question, names)
    if exact:
        return exact
    normalized = normalize_text(question)
    question_tokens = set(re.findall(r"\w+", normalized))
    full_matches = [
        name for name in names
        if len(normalize_text(name).split()) >= 2
        and set(normalize_text(name).split()).issubset(question_tokens)
    ]
    if len(full_matches) == 1:
        return full_matches[0]
    if len(full_matches) > 1:
        return None
    token_to_names = {}
    for name in names:
        for token in set(normalize_text(name).split()):
            if len(token) >= 4:
                token_to_names.setdefault(token, set()).add(name)
    candidates = [next(iter(owners)) for token, owners in token_to_names.items()
                  if len(owners) == 1 and re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", normalized)]
    return candidates[0] if len(set(candidates)) == 1 else None


def find_focus(question: str) -> str | None:
    normalized = normalize_text(question)
    aliases = [
        (r"\b(value|1890)\b", "Value"),
        (r"\b(above core)\b", "Above Core"),
        (r"\b(core)\b", "Core"),
        (r"\b(premium)\b", "Premium"),
        (r"\b(latones? 710)\b", "Latones 710"),
        (r"\b(balanced choices?)\b", "Balanced Choices"),
        (r"\b(nabs)\b", "Nabs"),
        (r"\b(total cza|cervezas?)\b", "Total CZA"),
    ]
    return next((focus for pattern, focus in aliases if re.search(pattern, normalized)), None)


def is_route_question(question: str) -> bool:
    return bool(re.search(r"\b(que|cual|cuales)\s+rutas?\b", normalize_text(question)))


def find_sku(question: str, options) -> str | None:
    normalized = normalize_text(question)
    caliber_match = re.search(r"(?<!\d)(250|269|275|330|354|355|473|500|710|1000|1500|2000|3000)\s*(?:cc|ml)?(?!\d)", normalized)
    caliber = caliber_match.group(1) if caliber_match else None
    if caliber:
        if re.search(r"\bpure\s*gold\b", normalized) and caliber in {"330", "473"}:
            return "PURE GOLD 330/PORRON" if caliber == "330" else "PURE GOLD 473 LATA"
        if re.search(r"\bred[\s-]*bu+l+\b|\br[\s-]*b\b", normalized):
            return f"RED BULL {caliber}"
        if re.search(r"\bmich(?:e|a)?lob\b", normalized):
            return f"MICHELOB ULTRA {caliber}"
        if re.search(r"\bpepsi\s*black\b|\bpep\s*bl\b", normalized):
            return f"PEPSI BLACK {caliber}"
        brands = [option[:-6].strip() for option in options if option.endswith(" TODOS") and option != "269 TODOS"]
        matched = [brand for brand in brands if re.search(r"(?<!\w)" + re.escape(normalize_text(brand)) + r"(?!\w)", normalized)]
        if matched:
            return f"{max(matched, key=len)} {caliber}"
        if re.search(r"\bqulmes\b|\bkilmes\b", normalized):
            return f"QUILMES {caliber}"
        family = {normalize_text(brand).split()[0] for brand in brands if brand and len(normalize_text(brand).split()[0]) >= 4}
        found_family = [token for token in family if re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", normalized)]
        if len(found_family) == 1:
            return f"{found_family[0].upper()} {caliber}"
        if caliber == "269" and re.search(r"\b269\b|\b269cc\b", normalized):
            return "269 TODOS"
    if re.search(r"\bred[\s-]*bu+l+\b|\br[\s-]*b\b", normalized):
        return "RED BULL TODOS"
    if re.search(r"\bmich(?:e|a)?lob\b", normalized):
        return "MICHELOB ULTRA TODOS"
    aliases = {
        "pure gold": "PURE GOLD TODOS",
        "pepsi black": "PEPSI BLACK TODOS",
        "black": "PEPSI BLACK TODOS",
        "gatorade": "GATORADE TODOS",
        "sin alcohol": "SIN ALCOHOL TODOS",
        "sin alchol": "SIN ALCOHOL TODOS",
        "latones 710": "LATONES 710",
    }
    for phrase, option in aliases.items():
        if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", normalized) and option in options:
            return option
    candidates = [option for option in options if option != "Todos" and normalize_text(option)]
    direct = find_named_entity(question, candidates)
    if direct:
        return direct
    brands = [option for option in candidates if option.endswith(" TODOS")]
    for option in sorted(brands, key=len, reverse=True):
        brand = normalize_text(option[:-6])
        if re.search(r"(?<!\w)" + re.escape(brand) + r"(?!\w)", normalized):
            return option
    return None


def asks_for_unsupported_period(question: str, current_month: int) -> bool:
    months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    normalized = normalize_text(question)
    return any(re.search(r"(?<!\w)" + month + r"(?!\w)", normalized) for index, month in enumerate(months, 1) if index != current_month)
