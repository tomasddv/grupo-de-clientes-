from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gdown
import streamlit as st

from kpi_data import load_dataset


DEFAULT_FILE_IDS = {
    "AUXILIARES.xlsx": "1zXhbWtT7K1tY43MmYz7oTTYifMgmLyFT",
    "RUTAS 7-26.xlsx": "12REZlhQOVsQVIEIAKJ6mFSsrtNCSK7s8",
    "ventadiaria.txt": "190CTcpwpXnb3r8jBMnwDYJVWsED8hVI2",
    "plantillaClientesAR.xlsx": "1GuRrGKlb7SLjI9h81XssZTpWzgPUrpRb",
    "reporte de clientes.xlsx": "1wMDck39W-Of-4HESCy6WXDWtnW02Swdz",
}
REQUIRED_FILES = {"AUXILIARES.xlsx", "RUTAS 7-26.xlsx", "ventadiaria.txt"}


def _file_id(name: str) -> str:
    try:
        configured = st.secrets.get("kpi_file_ids", {}).get(name)
    except Exception:
        configured = None
    return str(configured or DEFAULT_FILE_IDS[name])


@st.cache_data(ttl=3600, show_spinner=False)
def load_kpi_dataset():
    local_dir = os.environ.get("KPI_DATA_DIR", "").strip()
    if local_dir:
        return load_dataset(local_dir)

    with tempfile.TemporaryDirectory(prefix="consulta_kpi_") as temp_dir:
        def download(item):
            name, file_id = item
            target = Path(temp_dir) / name
            result = gdown.download(id=file_id, output=str(target), quiet=True, use_cookies=False)
            if not result or not target.exists() or target.stat().st_size == 0:
                if name in REQUIRED_FILES:
                    raise RuntimeError(f"No se pudo actualizar {name} desde Drive.")
                return

        files = [(name, _file_id(name)) for name in DEFAULT_FILE_IDS]
        with ThreadPoolExecutor(max_workers=3) as executor:
            list(executor.map(download, files))
        return load_dataset(temp_dir)
