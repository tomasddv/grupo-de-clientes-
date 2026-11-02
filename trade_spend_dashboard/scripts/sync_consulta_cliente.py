from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


FAMILIES = {
    "CORE RGB / 473": ("CORE", "CORE", "primary"),
    "VALUE LATA 473": ("VALUE", "LATA", "primary"),
    "VALUE LITRO 1000": ("VALUE", "LITRO", "primary"),
    "VALUE LATON 710": ("VALUE", "LATON", "extra"),
    "CORE 269": ("CORE 269", "CORE 269", "extra"),
}


def convert_rows(source: pd.DataFrame, date: str) -> pd.DataFrame:
    rows = []
    for row in source[source["familia"].isin(FAMILIES)].to_dict("records"):
        segmento, subsegmento, destination = FAMILIES[row["familia"]]
        details = json.loads(row.get("detalle") or "[]")
        group_lines = [
            f"{detail.get('grupo', '')} {detail.get('accion_id', '')} {detail.get('nombre', '')}".strip()
            for detail in details
        ]
        rows.append(
            {
                "fecha": date,
                "segmento": segmento,
                "subsegmento": subsegmento,
                "cliente": row["codigo"],
                "fantasia": row["fantasia"],
                "porcentaje_total": float(row["porcentaje_maximo"]) / 100,
                "supervisor": "",
                "promotor": row["promotor"],
                "ruta": row["ruta"],
                "grupos": " | ".join(group_lines),
                "origen": f"ERP {date}",
                "destination": destination,
            }
        )
    return pd.DataFrame(rows)


def build_group_summary(audit: pd.DataFrame, clients: pd.DataFrame, date: str) -> pd.DataFrame:
    target_families = set(FAMILIES)
    rows = []
    for action in audit[audit["familia"].isin(target_families)].to_dict("records"):
        action_id = str(action["accion_id"])
        count = clients["grupos"].str.contains(rf"(?:^|\|)\s*\d+\s+{action_id}(?:\s|$)", regex=True).sum()
        rows.append(
            {
                "fecha": date,
                "segmento": "CORE" if action["familia"] == "CORE RGB / 473" else "VALUE",
                "accion_id": action_id,
                "promo_compania": action["promo"],
                "descripcion": action["nombre"],
                "grupo": action["grupo"],
                "clientes": int(count),
                "origen": f"ERP {date}",
            }
        )
    return pd.DataFrame(rows).drop_duplicates(["accion_id", "grupo"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("discounts", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--date", default="2026-11-02")
    args = parser.parse_args()

    source = pd.read_csv(args.discounts, dtype=str).fillna("")
    audit = pd.read_csv(args.audit, dtype=str).fillna("")
    converted = convert_rows(source, args.date)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    primary = converted[converted["destination"] == "primary"].drop(columns="destination")
    extras = converted[converted["destination"] == "extra"].drop(columns="destination")
    primary.to_csv(args.output_dir / "client_percentages.csv", index=False, encoding="utf-8-sig")
    extras.to_csv(args.output_dir / "consulta_extra_discounts.csv", index=False, encoding="utf-8-sig")

    summary = build_group_summary(audit, converted, args.date)
    summary.to_csv(args.output_dir / "group_summary.csv", index=False, encoding="utf-8-sig")

    alerts = pd.DataFrame(
        [
            {
                "fecha": args.date,
                "estado": "ACTUALIZADO",
                "tipo": "ACCIONES NOVIEMBRE",
                "segmento": "CORE / VALUE",
                "detalle": "Snapshot sincronizado con la auditoría completa de acciones comerciales.",
                "clientes_actual": int(primary["cliente"].nunique()),
                "variacion": 0,
            }
        ]
    )
    alerts.to_csv(args.output_dir / "alerts.csv", index=False, encoding="utf-8-sig")
    print({"primary": len(primary), "extras": len(extras), "groups": len(summary)})


if __name__ == "__main__":
    main()
