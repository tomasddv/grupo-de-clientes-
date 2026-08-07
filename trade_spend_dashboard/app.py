from __future__ import annotations

from io import StringIO
from pathlib import Path

import gdown
import pandas as pd
import plotly.express as px
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import json


APP_DIR = Path(__file__).resolve().parent
LOCAL_DATA_DIR = APP_DIR / "data" / "processed"


st.set_page_config(
    page_title="Trade Spend",
    page_icon="%",
    layout="wide",
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


@st.cache_data(ttl=900)
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


clients, groups, alerts = load_data()

if clients.empty:
    st.error("No hay datos de clientes para mostrar.")
    st.stop()

clients["porcentaje_total"] = pd.to_numeric(clients["porcentaje_total"], errors="coerce").fillna(0)
clients["cliente"] = clients["cliente"].astype(str)

latest_date = clients["fecha"].max() if "fecha" in clients.columns else ""

st.title("Trade Spend")
st.caption(f"Fuente: Chess ERP / Drive. Ultima actualizacion: {latest_date}")

open_alerts = alerts[alerts["estado"].astype(str).str.lower().eq("alerta")] if not alerts.empty else pd.DataFrame()
if open_alerts.empty:
    st.success("Sin variaciones detectadas en acciones, grupos o clientes.")
else:
    st.warning(f"{len(open_alerts)} variaciones detectadas.")
    st.dataframe(open_alerts, use_container_width=True, hide_index=True)

with st.sidebar:
    st.header("Filtros")
    segment = st.multiselect("Segmento", unique_options(clients, "segmento"), default=unique_options(clients, "segmento"))
    subsegment = st.multiselect("Subsegmento", unique_options(clients, "subsegmento"))
    supervisor = st.multiselect("Supervisor", unique_options(clients, "supervisor"))
    promotor = st.multiselect("Promotor", unique_options(clients, "promotor"))
    ruta = st.multiselect("Ruta venta", unique_options(clients, "ruta"))
    search = st.text_input("Cliente o nombre")

filtered = clients.copy()
filtered = apply_filter(filtered, "segmento", segment)
filtered = apply_filter(filtered, "subsegmento", subsegment)
filtered = apply_filter(filtered, "supervisor", supervisor)
filtered = apply_filter(filtered, "promotor", promotor)
filtered = apply_filter(filtered, "ruta", ruta)

if search:
    needle = search.strip().lower()
    mask = filtered["cliente"].str.lower().str.contains(needle, na=False)
    if "fantasia" in filtered.columns:
        mask = mask | filtered["fantasia"].astype(str).str.lower().str.contains(needle, na=False)
    filtered = filtered[mask]

total_clients = filtered["cliente"].nunique()
avg_pct = filtered["porcentaje_total"].mean() if not filtered.empty else 0
max_pct = filtered["porcentaje_total"].max() if not filtered.empty else 0

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Clientes", f"{total_clients:,}".replace(",", "."))
kpi2.metric("% promedio", format_pct(avg_pct))
kpi3.metric("% maximo", format_pct(max_pct))
kpi4.metric("Segmentos", filtered["subsegmento"].nunique() if "subsegmento" in filtered.columns else 0)

left, right = st.columns([1, 1])

with left:
    summary = (
        filtered.groupby(["segmento", "subsegmento"], dropna=False)
        .agg(clientes=("cliente", "nunique"), porcentaje_promedio=("porcentaje_total", "mean"))
        .reset_index()
    )
    fig = px.bar(
        summary,
        x="subsegmento",
        y="clientes",
        color="segmento",
        text="clientes",
        title="Clientes por segmento",
    )
    fig.update_layout(yaxis_title="Clientes", xaxis_title="", legend_title="")
    st.plotly_chart(fig, use_container_width=True)

with right:
    pct_dist = (
        filtered.assign(porcentaje_label=filtered["porcentaje_total"].map(format_pct))
        .groupby(["segmento", "subsegmento", "porcentaje_label"], dropna=False)
        .agg(clientes=("cliente", "nunique"))
        .reset_index()
        .sort_values(["segmento", "subsegmento", "porcentaje_label"])
    )
    fig = px.bar(
        pct_dist,
        x="porcentaje_label",
        y="clientes",
        color="subsegmento",
        text="clientes",
        title="Distribucion de porcentajes",
    )
    fig.update_layout(yaxis_title="Clientes", xaxis_title="% total", legend_title="")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Grupos monitoreados")
st.dataframe(groups, use_container_width=True, hide_index=True)

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
st.dataframe(table.sort_values(["segmento", "subsegmento", "cliente"]), use_container_width=True, hide_index=True)
