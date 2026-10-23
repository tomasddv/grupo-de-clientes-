import argparse
import json
from pathlib import Path

import pandas as pd


FAMILIES = {
    "VALUE LATON 710": ("VALUE", "LATON"),
    "CORE 269": ("CORE 269", "CORE 269"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--date", default="2026-10-22")
    args = parser.parse_args()

    source = pd.read_csv(args.source, dtype=str).fillna("")
    rows = []
    for row in source[source["familia"].isin(FAMILIES)].to_dict("records"):
        segmento, subsegmento = FAMILIES[row["familia"]]
        details = json.loads(row.get("detalle") or "[]")
        group_lines = []
        for detail in details:
            group_lines.append(
                f"{detail.get('grupo', '')} {detail.get('accion_id', '')} {detail.get('nombre', '')}".strip()
            )
        rows.append(
            {
                "fecha": args.date,
                "segmento": segmento,
                "subsegmento": subsegmento,
                "cliente": row["codigo"],
                "fantasia": row["fantasia"],
                "porcentaje_total": float(row["porcentaje_maximo"]) / 100,
                "supervisor": "",
                "promotor": row["promotor"],
                "ruta": row["ruta"],
                "grupos": " | ".join(group_lines),
                "origen": f"ERP {args.date}",
            }
        )

    output = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False, encoding="utf-8-sig")
    print({"rows": len(output), "families": output["subsegmento"].value_counts().to_dict()})


if __name__ == "__main__":
    main()
