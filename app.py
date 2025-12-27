import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestión de Talleres", layout="wide")

# --- AUTENTICACIÓN SIMPLE ---
def check_password():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user_role = None

    if not st.session_state.logged_in:
        st.title("🔐 Acceso al Sistema")
        col1, col2 = st.columns([1,2])
        with col1:
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            
            if st.button("Ingresar"):
                # VALIDACIÓN DE CREDENCIALES
                if username == "admin" and password == st.secrets["passwords"]["admin"]:
                    st.session_state.logged_in = True
                    st.session_state.user_role = "admin"
                    st.rerun()
                elif username == "usuario" and password == st.secrets["passwords"]["user"]:
                    st.session_state.logged_in = True
                    st.session_state.user_role = "editor"
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")
        return False
    return True

if not check_password():
    st.stop()

# --- BARRA LATERAL (LOGOUT Y DATOS) ---
st.sidebar.write(f"👤 Conectado como: **{st.session_state.user_role.upper()}**")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.rerun()

# --- CONEXIÓN A GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    # Leemos la hoja. Si tu hoja se llama diferente de "Hoja 1", cámbialo aquí.
    data = conn.read(worksheet="Hoja 1", usecols=list(range(9)), ttl=5)
    df = pd.DataFrame(data)
    # CORRECCIÓN: dayfirst=True ayuda a pandas a entender fechas como 26/12/2025
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce', dayfirst=True)
except Exception as e:
    st.error(f"Error conectando a Google Sheets: {e}")
    st.stop()

st.title("🏫 Base de Datos de Talleres")

# --- FILTROS DE BÚSQUEDA ---
filtro = st.text_input("🔍 Buscar por CCT o Nombre del Plantel", placeholder="Escribe aquí...")

if filtro:
    mask = df['CCT'].astype(str).str.contains(filtro, case=False, na=False) | \
           df['Plantel'].astype(str).str.contains(filtro, case=False, na=False)
    df_visible = df[mask]
else:
    df_visible = df

# --- CONFIGURACIÓN DE PERMISOS DE COLUMNAS ---
es_admin = (st.session_state.user_role == "admin")

column_config = {
    "No": st.column_config.TextColumn("No.", disabled=True),
    "CCT": st.column_config.TextColumn("CCT", disabled=not es_admin),
    
    # CORRECCIÓN: SelectboxColumn en lugar de SelectColumn
    "Nivel": st.column_config.SelectboxColumn(
        "Nivel", 
        options=["PREESCOLAR", "PRIMARIA", "SECUNDARIA", "MEDIA SUPERIOR", "LICENCIATURA"], 
        disabled=not es_admin
    ),
    "Turno": st.column_config.SelectboxColumn(
        "Turno", 
        options=["MATUTINO", "VESPERTINO", "MIXTO"], 
        disabled=not es_admin
    ),
    "Plantel": st.column_config.TextColumn("Plantel", disabled=not es_admin),
    "Direccion": st.column_config.TextColumn("Dirección", disabled=not es_admin),
    
    # Campos editables por todos
    "Sesiones": st.column_config.NumberColumn("Sesiones", min_value=0, step=1),
    "Taller": st.column_config.TextColumn("Nombre Taller"),
    "Fecha": st.column_config.DateColumn("Fecha")
}

# --- EDITOR DE DATOS ---
st.info("💡 Haz doble clic en una celda para editarla.")

edited_df = st.data_editor(
    df_visible,
    column_config=column_config,
    num_rows="dynamic" if es_admin else "fixed",
    use_container_width=True,
    hide_index=True,
    key="data_editor"
)

# --- BOTÓN DE GUARDADO ---
if st.button("💾 Guardar Cambios en la Nube"):
    try:
        # 1. Unificar datos
        if filtro:
            df.update(edited_df)
            final_df_to_upload = df
        else:
            final_df_to_upload = edited_df
        
        # --- NUEVO: AUTO-GENERADOR DE ID (No.) ---
        # Esto soluciona que se borren filas si no pones el número
        # Convertimos la columna 'No' a números para poder sumar
        # (Los vacíos se vuelven 0 temporalmente para calcular el máximo)
        numeros_existentes = pd.to_numeric(final_df_to_upload['No'], errors='coerce').fillna(0)
        siguiente_id = int(numeros_existentes.max()) + 1
        
        # Recorremos el DataFrame y si vemos un 'No' vacío, le ponemos el número
        # Necesitamos reiniciar el índice para iterar correctamente
        final_df_to_upload = final_df_to_upload.reset_index(drop=True)
        
        for index, row in final_df_to_upload.iterrows():
            val_no = str(row['No'])
            # Si está vacío, es None, o es "nan", le asignamos ID
            if val_no == "" or val_no == "None" or val_no == "nan" or pd.isna(row['No']):
                final_df_to_upload.at[index, 'No'] = siguiente_id
                siguiente_id += 1
        # ----------------------------------------

        # 2. Limpieza de valores vacíos (evita errores en API)
        final_df_to_upload = final_df_to_upload.fillna("")
        
        # 3. Formatear fecha
        try:
            final_df_to_upload['Fecha'] = pd.to_datetime(final_df_to_upload['Fecha'], dayfirst=True).dt.strftime('%d/%m/%Y')
        except:
            pass 

        # 4. Guardar en Hoja 1
        conn.update(worksheet="Hoja 1", data=final_df_to_upload)
        
        # 5. Limpiar caché y recargar
        st.cache_data.clear()
        st.success("¡Guardado! El sistema asignó números automáticamente a los registros nuevos.")
        
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        
# --- SECCIÓN DE ESTADÍSTICAS ---
st.divider()
with st.expander("📊 Ver Estadísticas"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Filtrar periodo")
        d_inicio = st.date_input("Desde", date(2024, 1, 1))
        d_fin = st.date_input("Hasta", date.today())
        
        mask_fecha = (df['Fecha'].dt.date >= d_inicio) & (df['Fecha'].dt.date <= d_fin)
        df_stats = df[mask_fecha]
        
        st.metric("Total Talleres", len(df_stats))
        st.metric("Total Sesiones", df_stats['Sesiones'].sum())
        
    with col2:
        if not df_stats.empty:
            st.subheader("Talleres por Nivel")
            st.bar_chart(df_stats['Nivel'].value_counts())
        else:
            st.write("No hay datos en este rango.")