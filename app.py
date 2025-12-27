import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestión de Talleres", layout="wide")

# --- AUTENTICACIÓN SIMPLE ---
# Esto revisa si la contraseña ingresada coincide con la que guardaremos en Secrets
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
                # Admin: Puede editar todo y ver todo
                if username == "admin" and password == st.secrets["passwords"]["admin"]:
                    st.session_state.logged_in = True
                    st.session_state.user_role = "admin"
                    st.rerun()
                # Usuario Normal: Solo edita ciertos campos
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
# ttl=5 significa que guarda caché 5 segundos para no saturar la API
conn = st.connection("gsheets", type=GSheetsConnection)

try:
    # Leemos la hoja. Si tu hoja se llama diferente de "Hoja 1", cámbialo aquí.
    data = conn.read(worksheet="Hoja 1", usecols=list(range(9)), ttl=5)
    df = pd.DataFrame(data)
    # Aseguramos que la fecha sea datetime
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
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
# Si es admin, puede editar todo (disabled=False). Si es editor, algunas cosas True (bloqueadas).
es_admin = (st.session_state.user_role == "admin")

column_config = {
    "No": st.column_config.TextColumn("No.", disabled=True), # Nadie edita el ID manualmente
    "CCT": st.column_config.TextColumn("CCT", disabled=not es_admin),
    "Nivel": st.column_config.SelectColumn(
        "Nivel", 
        options=["PREESCOLAR", "PRIMARIA", "SECUNDARIA", "MEDIA SUPERIOR", "LICENCIATURA"], 
        disabled=not es_admin
    ),
    "Turno": st.column_config.SelectColumn(
        "Turno", 
        options=["MATUTINO", "VESPERTINO", "MIXTO"], 
        disabled=not es_admin
    ),
    "Plantel": st.column_config.TextColumn("Plantel", disabled=not es_admin),
    "Direccion": st.column_config.TextColumn("Dirección", disabled=not es_admin),
    
    # Estos campos son editables para ambos roles
    "Sesiones": st.column_config.NumberColumn("Sesiones", min_value=0, step=1),
    "Taller": st.column_config.TextColumn("Nombre Taller"),
    "Fecha": st.column_config.DateColumn("Fecha")
}

# --- EDITOR DE DATOS ---
st.info("💡 Haz doble clic en una celda para editarla.")

edited_df = st.data_editor(
    df_visible,
    column_config=column_config,
    num_rows="dynamic" if es_admin else "fixed", # Solo admin agrega filas nuevas
    use_container_width=True,
    hide_index=True,
    key="data_editor"
)

# --- BOTÓN DE GUARDADO ---
if st.button("💾 Guardar Cambios en la Nube"):
    try:
        # Lógica para guardar:
        # 1. Si hubo filtro, necesitamos actualizar solo esas filas en el DF original
        # 2. Si no hubo filtro, reemplazamos todo con lo editado
        
        if filtro:
            # Actualizamos el dataframe original con los cambios del filtrado
            # Usamos los índices para mapear (esto requiere que no resetees indices al filtrar)
            df.update(edited_df)
            final_df_to_upload = df
        else:
            final_df_to_upload = edited_df
            
        # Formatear fecha a string para que Google Sheets no se vuelva loco
        final_df_to_upload['Fecha'] = final_df_to_upload['Fecha'].dt.strftime('%Y-%m-%d')
        
        conn.update(worksheet="Hoja 1", data=final_df_to_upload)
        st.success("¡Datos actualizados correctamente en Google Drive!")
        st.balloons() # Un efecto visual bonito
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
        
        # Filtramos para estadisticas
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