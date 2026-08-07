from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "processed"


def normalize_client(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def load_value(path: Path, date: str) -> pd.DataFrame:
    rows = []
    for sheet_name, subsegment in [("litro %", "LITRO"), ("lata %", "LATA")]:
        df = pd.read_excel(path, sheet_name=sheet_name)
        for _, row in df.iterrows():
            rows.append(
                {
                    "fecha": date,
                    "segmento": "VALUE",
                    "subsegmento": subsegment,
                    "cliente": normalize_client(row.get("CLIENTE")),
                    "fantasia": row.get("FANTASIA", ""),
                    "porcentaje_total": row.get("%", 0),
                    "supervisor": row.get("SUPERVISOR", ""),
                    "promotor": row.get("PROMOTOR", ""),
                    "ruta": row.get("RUTA", ""),
                    "grupos": "",
                    "origen": "ERP",
                }
            )
    return pd.DataFrame(rows)


def load_core(path: Path, date: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="% CORE por cliente")
    return pd.DataFrame(
        {
            "fecha": date,
            "segmento": "CORE",
            "subsegmento": "CORE",
            "cliente": df["CLIENTE"].map(normalize_client),
            "fantasia": df["RAZÓN SOCIAL"],
            "porcentaje_total": df["Beneficio máximo total"],
            "supervisor": "",
            "promotor": "",
            "ruta": "",
            "grupos": df.get("Grupos", ""),
            "origen": df.get("Origen/Ajuste", "ERP"),
        }
    )


def load_client_master(path: Path | None) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame()
    raw = pd.read_excel(path, sheet_name="Clientes", header=1)
    wanted = {
        "Cliente": "cliente",
        "Nombre de fantasia": "fantasia_master",
        "Fuerza de Venta": "promotor",
        "Código Ruta Vta.": "ruta",
        "Descripción Ruta Vta.": "ruta_descripcion",
    }
    available = [column for column in wanted if column in raw.columns]
    master = raw[available].rename(columns=wanted)
    if "cliente" not in master.columns:
        return pd.DataFrame()
    master["cliente"] = master["cliente"].map(normalize_client)
    master = master[master["cliente"].ne("")]
    if "ruta_descripcion" in master.columns:
        master["promotor"] = master["ruta_descripcion"].map(extract_promoter)
        master["ruta"] = master.apply(
            lambda row: f"{row.get('ruta', '')} - {row.get('ruta_descripcion', '')}".strip(" -"),
            axis=1,
        )
        master = master.drop(columns=["ruta_descripcion"])
    if "promotor" not in master.columns:
        master["promotor"] = ""
    master["supervisor"] = ""
    return master.drop_duplicates("cliente")


def extract_promoter(route_description) -> str:
    if pd.isna(route_description):
        return ""
    text = str(route_description).strip()
    match = re.search(r"\bVE\s+(\d{2,3})\s+(.+?)\s+\d+\b", text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)} {match.group(2).strip()}".upper()
    return text


def enrich_clients(clients: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    if master.empty:
        return clients
    enriched = clients.merge(master, on="cliente", how="left", suffixes=("", "_master"))
    enriched = enriched.replace({"": pd.NA})
    enriched["fantasia"] = enriched["fantasia"].combine_first(enriched["fantasia_master"])
    for column in ["supervisor", "promotor", "ruta"]:
        master_column = f"{column}_master"
        if master_column in enriched.columns:
            enriched[column] = enriched[master_column].combine_first(enriched[column])
    drop_columns = [column for column in enriched.columns if column.endswith("_master")]
    return enriched.drop(columns=drop_columns)


def load_group_summary(value_path: Path, core_path: Path, date: str) -> pd.DataFrame:
    value_groups = pd.read_excel(value_path, sheet_name="Control descargas")
    value_groups = value_groups.rename(
        columns={
            "Identificador": "accion_id",
            "Descripción": "descripcion",
            "Filas clientes": "clientes",
            "Archivo": "grupo",
        }
    )
    value_groups["fecha"] = date
    value_groups["segmento"] = "VALUE"
    value_groups = value_groups[["fecha", "segmento", "accion_id", "descripcion", "grupo", "clientes", "Origen"]]
    value_groups = value_groups.rename(columns={"Origen": "origen"})

    core_detail = pd.read_excel(core_path, sheet_name="Detalle clientes")
    core_groups = (
        core_detail.groupby(["Grupo", "Descripción"], dropna=False)
        .agg(clientes=("CLIENTE", "nunique"), origen=("Origen", lambda s: ", ".join(sorted(set(map(str, s))))))
        .reset_index()
    )
    core_groups["fecha"] = date
    core_groups["segmento"] = "CORE"
    core_groups["accion_id"] = ""
    core_groups = core_groups.rename(columns={"Grupo": "grupo", "Descripción": "descripcion"})
    core_groups = core_groups[["fecha", "segmento", "accion_id", "descripcion", "grupo", "clientes", "origen"]]

    return pd.concat([value_groups, core_groups], ignore_index=True)


def build_alerts(group_summary: pd.DataFrame, date: str) -> pd.DataFrame:
    alerts = []
    for _, row in group_summary.iterrows():
        alerts.append(
            {
                "fecha": date,
                "estado": "ok",
                "tipo": "grupo_clientes",
                "segmento": row["segmento"],
                "detalle": f"{row['grupo']} - {row['descripcion']}",
                "clientes_actual": row["clientes"],
                "variacion": 0,
            }
        )
    return pd.DataFrame(alerts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--value-workbook", required=True, type=Path)
    parser.add_argument("--core-workbook", required=True, type=Path)
    parser.add_argument("--client-master", type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    clients = pd.concat(
        [load_value(args.value_workbook, args.date), load_core(args.core_workbook, args.date)],
        ignore_index=True,
    )
    clients = clients[clients["cliente"].ne("")]
    clients["porcentaje_total"] = pd.to_numeric(clients["porcentaje_total"], errors="coerce").fillna(0)
    clients = enrich_clients(clients, load_client_master(args.client_master))

    group_summary = load_group_summary(args.value_workbook, args.core_workbook, args.date)
    alerts = build_alerts(group_summary, args.date)

    clients.to_csv(args.output_dir / "client_percentages.csv", index=False, encoding="utf-8-sig")
    group_summary.to_csv(args.output_dir / "group_summary.csv", index=False, encoding="utf-8-sig")
    alerts.to_csv(args.output_dir / "alerts.csv", index=False, encoding="utf-8-sig")

    print(f"CSV generados en {args.output_dir}")


if __name__ == "__main__":
    main()
