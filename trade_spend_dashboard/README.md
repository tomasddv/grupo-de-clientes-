# Dashboard Trade Spend

Dashboard Streamlit para controlar acciones comerciales VALUE y CORE desde archivos alimentados por Drive.

## Que muestra

- Alertas si cambian acciones, grupos o clientes dentro de grupos.
- VALUE separado en `LITRO` y `LATA`.
- CORE usando solo `Beneficio máximo`.
- Filtros por supervisor, promotor y ruta cuando esos campos existan en el maestro de clientes.
- Tabla por cliente con codigo, fantasia/razon social y porcentaje total.

## Datos esperados

El dashboard lee estos CSV:

- `client_percentages.csv`
- `group_summary.csv`
- `alerts.csv`

Si no hay URLs configuradas en `.streamlit/secrets.toml`, usa los archivos locales en `data/processed`.

## Ejecucion local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## App para supervisores/promotores

Para crear un segundo link solo de consulta por codigo de cliente en Streamlit Cloud, usar el mismo repositorio y seleccionar este archivo como `Main file path`:

```text
trade_spend_dashboard/consulta_cliente.py
```

Esta app lee los mismos CSV de Drive y muestra una pantalla simple para celular con CORE, VALUE LITRO y VALUE LATA por cliente.

La pantalla incluye un boton hacia el asistente de compradores y no compradores. El asistente consulta la venta diaria, rutas, auxiliares y plantilla de clientes de Drive con las mismas reglas de SKU/focos del tablero de promotores. Para habilitarlo, configurar `kpi_assistant_access_code` en los secretos de Streamlit Cloud (no en GitHub). Los IDs de los archivos se pueden reemplazar en `[kpi_file_ids]` si cambian. Los datos quedan en cache durante una hora; para pruebas locales se puede usar `KPI_DATA_DIR` y `KPI_ASSISTANT_ACCESS_CODE`.

## Drive

La carpeta detectada para datos fue:

`BEES Vision - Datos Streamlit`

`https://drive.google.com/drive/folders/1Dqgsy8fQUlJR-zzsAuzFGLrdygGuxTYU`

Para produccion, dejar los tres CSV en esa carpeta y configurar sus URLs en Streamlit Cloud o usar una service account con permisos sobre la carpeta.

CSV iniciales subidos:

- `trade_spend_client_percentages.csv`: `1Eg8bu_YBx3tiWz1_NgkzvlFyxvtrCbRT`
- `trade_spend_group_summary.csv`: `1yJGeYgMPrgy1xS9JIKQAjg1yIM0xn_Hj`
- `trade_spend_alerts.csv`: `1-wpjd-DgpM4H0RknUPa-UkOKdmptwlKH`

## Actualizacion diaria

El flujo recomendado es:

1. `scripts/prepare_snapshot.py` toma los excels generados desde Chess ERP.
2. Genera los tres CSV limpios.
3. Una tarea diaria actualiza esos CSV en Drive.
4. Streamlit vuelve a leerlos y muestra las alertas.

El scraping/login del ERP debe correr con credenciales en variables de entorno o secrets; no se deben guardar usuarios ni claves dentro del repositorio.
