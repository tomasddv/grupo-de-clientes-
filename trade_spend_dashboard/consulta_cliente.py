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
    page_title="Consulta Trade Spend",
    page_icon="%",
    layout="centered",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 680px;
        padding-top: 1.4rem;
        padding-left: 0.9rem;
        padding-right: 0.9rem;
    }
    h1 {
        font-size: 1.9rem !important;
        margin-bottom: 0.25rem;
    }
    div[data-testid="stTextInput"] input {
        font-size: 1.3rem;
        min-height: 3rem;
    }
    div[data-testid="stFormSubmitButton"] button {
        min-height: 3rem;
        font-size: 1.05rem;
        font-weight: 700;
    }
    .assistant-hero {
        display: flex;
        gap: 14px;
        align-items: center;
        border: 1px solid rgba(120, 120, 120, 0.22);
        border-radius: 8px;
        padding: 14px;
        margin: 10px 0 18px;
        background: linear-gradient(135deg, rgba(18, 119, 192, 0.16), rgba(41, 171, 135, 0.14));
    }
    .mascot {
        position: relative;
        width: 74px;
        min-width: 74px;
        height: 74px;
        border-radius: 50%;
        background: #1277c0;
        box-shadow: inset 0 -8px 0 rgba(0, 0, 0, 0.14);
    }
    .mascot::before,
    .mascot::after {
        content: "";
        position: absolute;
        top: 25px;
        width: 9px;
        height: 9px;
        border-radius: 50%;
        background: white;
    }
    .mascot::before {
        left: 22px;
    }
    .mascot::after {
        right: 22px;
    }
    .mascot-mark {
        position: absolute;
        left: 0;
        right: 0;
        bottom: 13px;
        color: white;
        font-size: 1.6rem;
        font-weight: 900;
        text-align: center;
        line-height: 1;
    }
    .hero-copy {
        min-width: 0;
    }
    .hero-copy strong {
        display: block;
        font-size: 1.08rem;
        margin-bottom: 4px;
    }
    .client-card {
        border: 1px solid rgba(120, 120, 120, 0.24);
        border-radius: 8px;
        padding: 16px;
        margin: 12px 0;
        background: rgba(120, 120, 120, 0.08);
    }
    .client-name {
        font-size: 1.2rem;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .muted {
        opacity: 0.78;
        font-size: 0.95rem;
    }
    .discount-card {
        border: 1px solid rgba(120, 120, 120, 0.24);
        border-radius: 8px;
        padding: 16px;
        margin: 12px 0;
        background: rgba(120, 120, 120, 0.06);
    }
    .discount-title {
        font-size: 1rem;
        font-weight: 700;
        margin-bottom: 4px;
    }
    .discount-pct {
        font-size: 2.1rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .answer {
        font-size: 1.05rem;
        line-height: 1.45;
        margin-top: 8px;
    }
    @media (max-width: 520px) {
        .assistant-hero {
            align-items: flex-start;
        }
        .mascot {
            width: 62px;
            min-width: 62px;
            height: 62px;
        }
        .mascot::before,
        .mascot::after {
            top: 21px;
        }
        .mascot::before {
            left: 18px;
        }
        .mascot::after {
            right: 18px;
        }
        .mascot-mark {
            bottom: 10px;
            font-size: 1.35rem;
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
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    client_url = _secret("drive.client_percentages_url")
    groups_url = _secret("drive.group_summary_url")
    service_account_json = _secret("drive.service_account_json")
    client_file_id = _secret("drive.client_percentages_file_id")
    groups_file_id = _secret("drive.group_summary_file_id")

    if service_account_json and client_file_id and groups_file_id:
        clients = _read_csv_from_private_drive(client_file_id, service_account_json)
        groups = _read_csv_from_private_drive(groups_file_id, service_account_json)
        return clients, groups

    if client_url and groups_url:
        clients = _read_csv_from_url(client_url)
        groups = _read_csv_from_url(groups_url)
        return clients, groups

    clients = pd.read_csv(LOCAL_DATA_DIR / "client_percentages.csv")
    groups = pd.read_csv(LOCAL_DATA_DIR / "group_summary.csv")
    return clients, groups


def normalize_code(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def extract_group_code(value: str) -> str:
    match = re.match(r"\s*(\d+)", str(value or ""))
    return match.group(1) if match else ""


def format_pct(value: float) -> str:
    if pd.isna(value):
        return "0.00%"
    return f"{value * 100:.2f}%"


def prepare_clients(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["porcentaje_total"] = pd.to_numeric(df["porcentaje_total"], errors="coerce").fillna(0)
    df["cliente"] = df["cliente"].astype(str)
    for column in ["segmento", "subsegmento", "supervisor", "promotor", "ruta", "fantasia", "grupos", "origen"]:
        if column in df.columns:
            df[column] = df[column].fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    return df


def prepare_groups(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for column in ["segmento", "accion_id", "promo_compania", "descripcion", "grupo"]:
        if column in df.columns:
            df[column] = df[column].fillna("").astype(str).str.strip()
    return df


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


def build_action_lookup(groups: pd.DataFrame) -> dict[str, list[dict[str, str]]]:
    lookup: dict[str, list[dict[str, str]]] = {}
    for row in groups.to_dict("records"):
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


clients_raw, groups_raw = load_data()
if clients_raw.empty:
    st.error("No hay datos de clientes para consultar.")
    st.stop()

clients = prepare_clients(clients_raw)
groups = prepare_groups(groups_raw)
action_lookup = build_action_lookup(groups)
latest_date = clients["fecha"].max() if "fecha" in clients.columns else ""

st.title("Consulta Trade Spend")
st.caption(f"Actualizado: {latest_date}")
st.markdown(
    """
    <div class="assistant-hero">
        <div class="mascot"><div class="mascot-mark">%</div></div>
        <div class="hero-copy">
            <strong>Asistente de descuentos</strong>
            <div class="muted">Escribí un código de cliente y te digo qué porcentaje tiene en CORE, VALUE LITRO y VALUE LATA.</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.form("client_lookup", clear_on_submit=False):
    query = st.text_input("Codigo de cliente", placeholder="Ej: 3992")
    submitted = st.form_submit_button("Consultar", use_container_width=True)

code = normalize_code(query)
if submitted and not code:
    st.info("Ingresá un código de cliente.")
elif code:
    result = clients[clients["cliente"].map(normalize_code).eq(code)].copy()
    if result.empty:
        st.warning(f"No encontre el cliente {code} en el archivo actual.")
    else:
        result = result.sort_values(["segmento", "subsegmento"])
        first = result.iloc[0]
        st.markdown(
            f"""
            <div class="client-card">
                <div class="client-name">{code} - {first.get("fantasia", "")}</div>
                <div class="muted">{first.get("promotor", "")}</div>
                <div class="muted">{first.get("ruta", "")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        lines = []
        for _, row in result.iterrows():
            label = row["segmento"] if row["segmento"] == "CORE" else f"{row['segmento']} {row['subsegmento']}"
            pct_text = format_pct(row["porcentaje_total"])
            lines.append(f"{label}: {pct_text}")
            st.markdown(
                f"""
                <div class="discount-card">
                    <div class="discount-title">{label}</div>
                    <div class="discount-pct">{pct_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander(f"Acciones y grupos de {label}", expanded=False):
                for action_line in actions_for_client_row(row, action_lookup):
                    st.write(f"- {action_line}")

        st.markdown(
            f"""<div class="answer">Respuesta: el cliente <strong>{code}</strong> tiene {'; '.join(lines)}.</div>""",
            unsafe_allow_html=True,
        )
else:
    st.info("Escribí el código del cliente para ver sus descuentos.")
