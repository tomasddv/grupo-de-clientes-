from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path

from assistant_service import answer_question, resolve_promoter
from kpi_source import load_kpi_dataset


def render_assistant() -> None:
    if st.button("Volver a consulta de descuentos"):
        st.session_state["client_view"] = "lookup"
        st.rerun()
    st.title("Asistente comercial")

    with st.spinner("Preparando ventas y rutas..."):
        try:
            dataset = load_kpi_dataset()
        except Exception as exc:
            st.error(f"No se pudieron cargar las ventas y rutas: {exc}")
            st.stop()

    if not dataset["fechas"]:
        st.warning("No hay fechas de venta para consultar.")
        st.stop()

    promoters = dataset["promotores"]
    selected = st.session_state.get("kpi_assistant_promoter")
    if selected not in set(promoters["promotor"].dropna()):
        selected = None
        st.session_state.pop("kpi_assistant_promoter", None)

    if not selected:
        with st.form("kpi_assistant_identity"):
            identity = st.text_input("Tu nombre completo o código de vendedor")
            submitted = st.form_submit_button("Consultar mi cartera", use_container_width=True)
        if submitted:
            selected = resolve_promoter(identity, promoters)
            if selected:
                st.session_state["kpi_assistant_promoter"] = selected
                st.session_state["kpi_assistant_context"] = {"promoter": selected}
                st.session_state["kpi_assistant_history"] = []
                st.rerun()
            else:
                st.error("No encontré un promotor único con ese nombre o código. Revisá el dato en la planilla de vendedores.")
        st.stop()

    col_name, col_change = st.columns([3, 1])
    col_name.write(f"**Promotor:** {selected}")
    if col_change.button("Cambiar"):
        for key in ("kpi_assistant_promoter", "kpi_assistant_context", "kpi_assistant_history"):
            st.session_state.pop(key, None)
        st.rerun()

    last_date = max(dataset["fechas"])
    st.caption(f"Venta diaria actualizada hasta {last_date:%Y-%m-%d}")

    prompt = st.chat_input("Preguntá por clientes, compras, SKU o descuentos")
    if prompt:
        try:
            load_discounts = st.session_state["assistant_discount_loader"]
            data_dir = Path(st.session_state["assistant_discount_dir"])
            discounts, _ = load_discounts()
            extras_path = data_dir / "consulta_extra_discounts.csv"
            if extras_path.exists():
                discounts = pd.concat([discounts, pd.read_csv(extras_path, dtype=str).fillna("")], ignore_index=True)
        except Exception as exc:
            st.error(f"No se pudieron cargar los descuentos: {exc}")
            st.stop()
        answer, detail, context = answer_question(
            prompt, dataset, st.session_state.get("kpi_assistant_context"), fixed_promoter=selected, discounts=discounts
        )
        st.session_state["kpi_assistant_context"] = context
        st.session_state.setdefault("kpi_assistant_history", []).append((prompt, answer, detail))

    for question, answer, detail in st.session_state.get("kpi_assistant_history", []):
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            st.write(answer)
            if detail is not None and not detail.empty:
                st.dataframe(detail, use_container_width=True, hide_index=True)
