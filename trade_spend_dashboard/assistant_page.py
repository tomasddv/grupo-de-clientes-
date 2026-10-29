from __future__ import annotations

import hmac
import os

import streamlit as st

from assistant_service import answer_question
from kpi_source import load_kpi_dataset


def render_assistant() -> None:
    if st.button("Volver a consulta de descuentos"):
        st.session_state["client_view"] = "lookup"
        st.rerun()
    st.title("Asistente comercial")

    try:
        access_code = str(st.secrets.get("kpi_assistant_access_code", ""))
    except Exception:
        access_code = ""
    access_code = access_code or os.environ.get("KPI_ASSISTANT_ACCESS_CODE", "")
    if not access_code:
        st.error("El asistente todavía no tiene configurado su código de acceso en los secretos de la app.")
        st.stop()

    if not st.session_state.get("kpi_assistant_authorized"):
        with st.form("kpi_assistant_login"):
            provided_code = st.text_input("Código de acceso", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)
        if submitted:
            if hmac.compare_digest(provided_code, access_code):
                st.session_state["kpi_assistant_authorized"] = True
                st.rerun()
            else:
                st.error("Código incorrecto.")
        st.stop()

    with st.spinner("Preparando ventas y rutas..."):
        try:
            dataset = load_kpi_dataset()
        except Exception as exc:
            st.error(f"No se pudieron cargar las ventas y rutas: {exc}")
            st.stop()

    if not dataset["fechas"]:
        st.warning("No hay fechas de venta para consultar.")
        st.stop()

    last_date = max(dataset["fechas"])
    st.caption(f"Venta diaria actualizada hasta {last_date:%Y-%m-%d}")

    prompt = st.chat_input("Preguntá por clientes, promotores, SKU o focos")
    if prompt:
        answer, detail, context = answer_question(prompt, dataset, st.session_state.get("kpi_assistant_context"))
        st.session_state["kpi_assistant_context"] = context
        st.session_state.setdefault("kpi_assistant_history", []).append((prompt, answer, detail))

    for question, answer, detail in st.session_state.get("kpi_assistant_history", []):
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            st.write(answer)
            if detail is not None and not detail.empty:
                st.dataframe(detail, use_container_width=True, hide_index=True)
