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
    "ventadiaria.txt": "1I-vewZKeotS02twpDgSnmAbYjKT4mlXG",
    "plantillaClientesAR.xlsx": "1GuRrGKlb7SLjI9h81XssZTpWzgPUrpRb",
    "reporte de clientes.xlsx": "1wMDck39W-Of-4HESCy6WXDWtnW02Swdz",
}
REQUIRED_FILES = {"AUXILIARES.xlsx", "RUTAS 7-26.xlsx", "ventadiaria.txt"}
DEFAULT_DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1cukgXLUaPsEDK_yD7tSwgaBFZAbiDUot"


def _file_id(name: str) -> str:
    try:
        configured = st.secrets.get("kpi_file_ids", {}).get(name)
    except Exception:
        configured = None
    return str(configured or DEFAULT_FILE_IDS[name])


def current_daily_file_id() -> str:
    try:
        folder_url = st.secrets.get("kpi_drive_folder_url", DEFAULT_DRIVE_FOLDER_URL)
    except Exception:
        folder_url = DEFAULT_DRIVE_FOLDER_URL
    try:
        files = gdown.download_folder(
            url=str(folder_url), output=None, quiet=True, use_cookies=False, skip_download=True
        )
    except Exception as exc:
        raise RuntimeError("No se pudo consultar la carpeta de ventas en Drive.") from exc
    current = next(
        (file for file in files or [] if Path(str(file.path)).name.casefold() == "ventadiaria.txt"),
        None,
    )
    if current is None:
        raise RuntimeError("No se encontró ventadiaria.txt en la carpeta de Drive.")
    return str(current.id)


@st.cache_data(ttl=300, show_spinner=False)
def load_kpi_dataset():
    local_dir = os.environ.get("KPI_DATA_DIR", "").strip()
    if local_dir:
        return load_dataset(local_dir)

    with tempfile.TemporaryDirectory(prefix="consulta_kpi_") as temp_dir:
        def download(item):
            name, file_id = item
            target = Path(temp_dir) / name
            try:
                result = gdown.download(id=file_id, output=str(target), quiet=True, use_cookies=False)
            except Exception as exc:
                if name in REQUIRED_FILES:
                    raise RuntimeError(f"No se pudo actualizar {name} desde Drive.") from exc
                return
            if not result or not target.exists() or target.stat().st_size == 0:
                if name in REQUIRED_FILES:
                    raise RuntimeError(f"No se pudo actualizar {name} desde Drive.")
                return

        files = [
            (name, current_daily_file_id() if name == "ventadiaria.txt" else _file_id(name))
            for name in DEFAULT_FILE_IDS
        ]
        with ThreadPoolExecutor(max_workers=3) as executor:
            list(executor.map(download, files))
        return load_dataset(temp_dir)
