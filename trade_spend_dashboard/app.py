from __future__ import annotations

import io
import json
import re
from pathlib import Path

import gdown
import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


APP_DIR = Path(__file__).resolve().parent
LOCAL_DATA_DIR = APP_DIR / "data" / "processed"


st.set_page_config(
    page_title="Trade Spend",
    page_icon="%",
    layout="wide",
)

st.markdown(
    """
    <style>
    div[data-testid="stDataFrame"] {
        font-size: 17px;
    }
    div[data-testid="stDataFrame"] [role="gridcell"],
    div[data-testid="stDataFrame"] [role="columnheader"] {
        min-height: 42px;
    }
    .discount-card {
        border: 1px solid rgba(120, 120, 120, 0.22);
        border-radius: 8px;
        padding: 18px;
        margin: 10px 0 18px;
        background: rgba(120, 120, 120, 0.08);
    }
    .discount-card h3 {
        margin: 0 0 8px;
    }
    .discount-line {
        font-size: 1.1rem;
        margin: 8px 0;
    }
    .discount-total {
        font-size: 1.45rem;
        font-weight: 700;
    }
    @media (max-width: 720px) {
        .block-container {
            padding-top: 1.25rem;
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
        h1 {
            font-size: 1.8rem !important;
        }
        div[data-testid="stDataFrame"] {
            font-size: 15px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _secret(path: str, default: str = "") -> str:
    current = st.secrets
    for part in path.split("."):
        if part not in current:
            return default
        current = current[part]
    return str(current or default).strip()


def _read_csv_from_url(url: str) -> pd.DataFrame:
    if not url:
        return pd.DataFrame()
    content = gdown.download(url=url, quiet=True, fuzzy=True)
    if not content:
        return pd.DataFrame()
    return pd.read_csv(content)


def _read_csv_from_private_drive(file_id: str, service_account_json: str) -> pd.DataFrame:
    if not file_id or not service_account_json.strip():
        return pd.DataFrame()
    info = json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    service = build("drive", "v3", credentials=credentials)
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return pd.read_csv(buffer)


@st.cache_data(ttl=60)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    client_url = _secret("drive.client_percentages_url")
    groups_url = _secret("drive.group_summary_url")
    alerts_url = _secret("drive.alerts_url")
    service_account_json = _secret("drive.service_account_json")
    client_file_id = _secret("drive.client_percentages_file_id")
    groups_file_id = _secret("drive.group_summary_file_id")
    alerts_file_id = _secret("drive.alerts_file_id")

    if service_account_json and client_file_id and groups_file_id and alerts_file_id:
        clients = _read_csv_from_private_drive(client_file_id, service_account_json)
        groups = _read_csv_from_private_drive(groups_file_id, service_account_json)
        alerts = _read_csv_from_private_drive(alerts_file_id, service_account_json)
        return clients, groups, alerts

    if client_url and groups_url and alerts_url:
        clients = _read_csv_from_url(client_url)
        groups = _read_csv_from_url(groups_url)
        alerts = _read_csv_from_url(alerts_url)
        return clients, groups, alerts

    clients = pd.read_csv(LOCAL_DATA_DIR / "client_percentages.csv")
    groups = pd.read_csv(LOCAL_DATA_DIR / "group_summary.csv")
    alerts = pd.read_csv(LOCAL_DATA_DIR / "alerts.csv")
    return clients, groups, alerts


def format_pct(value: float) -> str:
    if pd.isna(value):
        return ""
    return f"{value * 100:.2f}%"


def unique_options(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str).str.strip()
    values = values[values.ne("")]
    return sorted(values.unique().tolist())


def apply_filter(df: pd.DataFrame, column: str, selected: list[str]) -> pd.DataFrame:
    if not selected or column not in df.columns:
        return df
    return df[df[column].astype(str).isin(selected)]


def normalize_code(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def extract_group_code(value: str) -> str:
    match = re.match(r"\s*(\d+)", str(value or ""))
    return match.group(1) if match else ""


def product_matches_action(client_row: pd.Series, action_row: pd.Series) -> bool:
    if client_row["segmento"] != action_row["segmento"]:
        return False
    if client_row["segmento"] != "VALUE":
        return True

    subsegment = str(client_row.get("subsegmento", "")).upper()
    description = str(action_row.get("descripcion", "")).upper()
    has_lata = "LATA" in description
    has_litro = "LITRO" in description or " LT " in f" {description} "
    if subsegment == "LATA":
        return has_lata or not has_litro
    if subsegment == "LITRO":
        return has_litro or not has_lata
    return True


def build_action_lookup(groups_df: pd.DataFrame) -> dict[str, list[dict[str, str]]]:
    if groups_df.empty or "grupo" not in groups_df.columns:
        return {}
    clean_groups = groups_df.copy()
    for column in ["segmento", "accion_id", "promo_compania", "descripcion", "grupo"]:
        if column in clean_groups.columns:
            clean_groups[column] = clean_groups[column].fillna("").astype(str).str.strip()

    lookup: dict[str, list[dict[str, str]]] = {}
    for row in clean_groups.to_dict("records"):
        group_code = extract_group_code(row.get("grupo", ""))
        if group_code:
            lookup.setdefault(group_code, []).append(row)
    return lookup


def actions_for_client_row(client_row: pd.Series, action_lookup: dict[str, list[dict[str, str]]]) -> list[str]:
    action_lines = []
    group_text = str(client_row.get("grupos", ""))
    for raw_group in [part.strip() for part in group_text.split("|") if part.strip()]:
        group_code = extract_group_code(raw_group)
        matches = [
            action
            for action in action_lookup.get(group_code, [])
            if product_matches_action(client_row, pd.Series(action))
        ]
        if matches:
            for action in matches:
                action_lines.append(
                    f"{action.get('accion_id', '')} / promo {action.get('promo_compania', '')}: "
                    f"{action.get('descripcion', '')} - grupo {group_code}"
                )
        else:
            action_lines.append(raw_group)
    return action_lines


def render_client_assistant(clients_df: pd.DataFrame, groups_df: pd.DataFrame) -> None:
    action_lookup = build_action_lookup(groups_df)
    st.subheader("Consulta por cliente")
    with st.form("client_assistant_form", clear_on_submit=False):
        query = st.text_input(
            "Codigo de cliente",
            placeholder="Ej: 3992",
            key="assistant_client_code",
        )
        submitted = st.form_submit_button("Consultar descuento", use_container_width=True)

    code = normalize_code(query)
    if not submitted and not code:
        return

    if not code:
        st.info("Ingresa un codigo de cliente para consultar.")
        return

    result = clients_df[clients_df["cliente"].map(normalize_code).eq(code)].copy()
    if result.empty:
        st.warning(f"No encontre el cliente {code} en el archivo actual.")
        return

    result = result.sort_values(["segmento", "subsegmento"])
    first = result.iloc[0]
    st.markdown(
        f"""
        <div class="discount-card">
            <h3>Cliente {code} - {first.get("fantasia", "")}</h3>
            <div>{first.get("promotor", "")} - {first.get("ruta", "")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for _, row in result.iterrows():
        title = row["segmento"] if row["segmento"] == "CORE" else f"{row['segmento']} {row['subsegmento']}"
        st.markdown(
            f"""
            <div class="discount-card">
                <div class="discount-line">{title}</div>
                <div class="discount-total">{format_pct(row["porcentaje_total"])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        action_lines = actions_for_client_row(row, action_lookup)
        if action_lines:
            with st.expander(f"Ver acciones y grupos de {title}", expanded=True):
                for action_line in action_lines:
                    st.write(f"- {action_line}")


clients, groups, alerts = load_data()

if clients.empty:
    st.error("No hay datos de clientes para mostrar.")
    st.stop()

clients["porcentaje_total"] = pd.to_numeric(clients["porcentaje_total"], errors="coerce").fillna(0)
clients["cliente"] = clients["cliente"].astype(str)
clients["cliente_num"] = pd.to_numeric(clients["cliente"], errors="coerce")
for text_column in ["segmento", "subsegmento", "supervisor", "promotor", "ruta", "fantasia", "grupos", "origen"]:
    if text_column in clients.columns:
        clients[text_column] = clients[text_column].fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

latest_date = clients["fecha"].max() if "fecha" in clients.columns else ""

st.title("Trade Spend")
st.caption(f"Fuente: Chess ERP / Drive. Ultima actualizacion: {latest_date}")

render_client_assistant(clients, groups)

open_alerts = alerts[alerts["estado"].astype(str).str.lower().eq("alerta")] if not alerts.empty else pd.DataFrame()
if open_alerts.empty:
    st.success("Sin variaciones detectadas en acciones, grupos o clientes.")
else:
    with st.expander(f"{len(open_alerts)} variaciones detectadas"):
        st.dataframe(open_alerts, use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("Filtros")
    segment = st.multiselect("Segmento", unique_options(clients, "segmento"), default=unique_options(clients, "segmento"))
    subsegment = st.multiselect("Subsegmento", unique_options(clients, "subsegmento"))
    supervisor = st.multiselect("Supervisor", unique_options(clients, "supervisor"))
    promotor = st.multiselect("Promotor", unique_options(clients, "promotor"))
    ruta = st.multiselect("Ruta venta", unique_options(clients, "ruta"))
    client_code = st.text_input("Codigo cliente")
    search = st.text_input("Nombre fantasia")

filtered = clients.copy()
filtered = apply_filter(filtered, "segmento", segment)
filtered = apply_filter(filtered, "subsegmento", subsegment)
filtered = apply_filter(filtered, "supervisor", supervisor)
filtered = apply_filter(filtered, "promotor", promotor)
filtered = apply_filter(filtered, "ruta", ruta)

if client_code:
    code = client_code.strip()
    filtered = filtered[filtered["cliente"].astype(str).str.strip().eq(code)]

if search:
    needle = search.strip().lower()
    if "fantasia" in filtered.columns:
        filtered = filtered[filtered["fantasia"].astype(str).str.lower().str.contains(needle, na=False)]

st.subheader("Clientes")
display_cols = [
    "segmento",
    "subsegmento",
    "cliente",
    "fantasia",
    "porcentaje_total",
    "supervisor",
    "promotor",
    "ruta",
    "grupos",
    "origen",
]
display_cols = [c for c in display_cols if c in filtered.columns]
table = filtered[display_cols].copy()
if "porcentaje_total" in table.columns:
    table["porcentaje_total"] = table["porcentaje_total"].map(format_pct)
st.dataframe(
    filtered.assign(porcentaje_total=filtered["porcentaje_total"].map(format_pct))
    .sort_values(["cliente_num", "segmento", "subsegmento"], na_position="last")[display_cols],
    use_container_width=True,
    hide_index=True,
    height=760,
    row_height=44,
    column_config={
        "segmento": st.column_config.TextColumn("Segmento", width="small"),
        "subsegmento": st.column_config.TextColumn("Subsegmento", width="small"),
        "cliente": st.column_config.TextColumn("Cliente", width="small"),
        "fantasia": st.column_config.TextColumn("Nombre fantasia", width="large"),
        "porcentaje_total": st.column_config.TextColumn("%", width="small"),
        "supervisor": st.column_config.TextColumn("Supervisor", width="medium"),
        "promotor": st.column_config.TextColumn("Promotor", width="medium"),
        "ruta": st.column_config.TextColumn("Ruta venta", width="large"),
        "grupos": st.column_config.TextColumn("Grupos", width="large"),
        "origen": st.column_config.TextColumn("Origen", width="medium"),
    },
)
