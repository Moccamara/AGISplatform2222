import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw, MousePosition
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
from shapely.geometry import shape
from branca.element import MacroElement
from jinja2 import Template

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(layout="wide", page_title="Geospatial Enterprise Solution")
st.title("🌍 Geospatial Enterprise Solution")

# =========================================================
# USERS AND ROLES
# =========================================================
USERS = {
    "admin": {"password": "admin2025", "role": "Admin"},
    "customer": {"password": "cust2025", "role": "Customer"},
}

# =========================================================
# SESSION INIT
# =========================================================
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None

# =========================================================
# LOGOUT
# =========================================================
def logout():
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None
    st.rerun()

# =========================================================
# LOGIN
# =========================================================
if not st.session_state.auth_ok:
    st.sidebar.header("🔐 Login")
    username = st.sidebar.selectbox("User", list(USERS.keys()))
    password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login", use_container_width=True):
        if password == USERS[username]["password"]:
            st.session_state.auth_ok = True
            st.session_state.username = username
            st.session_state.user_role = USERS[username]["role"]
            st.success("✅ Login successful")
            st.rerun()
        else:
            st.sidebar.error("❌ Incorrect password")
    st.stop()

# =========================================================
# LOAD SE POLYGONS
# =========================================================
SE_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/SE.geojson"

@st.cache_data(show_spinner=False)
def load_se_data(url):
    gdf = gpd.read_file(url)
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)
    gdf.columns = gdf.columns.str.lower().str.strip()
    gdf = gdf.rename(columns={"lregion":"region","lcercle":"cercle","lcommune":"commune"})
    gdf = gdf[gdf.is_valid & ~gdf.is_empty]
    for col in ["region","cercle","commune","idse_new"]:
        if col not in gdf.columns:
            gdf[col] = ""
    for col in ["pop_se","pop_se_ct"]:
        if col not in gdf.columns:
            gdf[col] = 0
    return gdf

gdf = load_se_data(SE_URL)

# =========================================================
# LOAD CONCESSION POINTS
# =========================================================
POINTS_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/concession.csv"

@st.cache_data(show_spinner=False)
def load_points_from_github(url):
    df = pd.read_csv(url)
    df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["LON"] = pd.to_numeric(df["LON"], errors="coerce")
    df = df.dropna(subset=["LAT","LON"])
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["LON"], df["LAT"]),
        crs="EPSG:4326"
    )

if st.session_state.points_gdf is None:
    st.session_state.points_gdf = load_points_from_github(POINTS_URL)

points_gdf = st.session_state.points_gdf

# =========================================================
# SAFE SPATIAL JOIN
# =========================================================
def safe_sjoin(points, polygons, how="inner", predicate="intersects"):
    if points is None or polygons is None or points.empty or polygons.empty:
        return gpd.GeoDataFrame()
    for col in ["index_right", "_r"]:
        if col in polygons.columns:
            polygons = polygons.drop(columns=[col])
    return gpd.sjoin(points, polygons, how=how, predicate=predicate)

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown(f"**👤 User:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

    st.markdown("### 🗂 Attribute Query")
    region = st.selectbox("Region", sorted(gdf["region"].unique()))
    gdf_r = gdf[gdf["region"] == region]

    cercle = st.selectbox("Cercle", sorted(gdf_r["cercle"].unique()))
    gdf_c = gdf_r[gdf_r["cercle"] == cercle]

    commune = st.selectbox("Commune", sorted(gdf_c["commune"].unique()))
    gdf_commune = gdf_c[gdf_c["commune"] == commune]

    idse_list = ["No filter"] + sorted(gdf_commune["idse_new"].unique())
    idse_selected = st.selectbox("Unit_Geo", idse_list)
    gdf_idse = gdf_commune if idse_selected=="No filter" else gdf_commune[gdf_commune["idse_new"]==idse_selected]

    # ✅ LEGEND TOGGLE (NEW)
    st.markdown("### 🧭 Map Legend")
    show_legend = st.checkbox("Show / Hide Legend", value=True)

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(location=[(miny+maxy)/2, (minx+maxx)/2], zoom_start=18)

folium.TileLayer("OpenStreetMap").add_to(m)
folium.GeoJson(
    gdf_idse,
    name="SE",
    style_function=lambda x: {"color":"blue","weight":2,"fillOpacity":0.15},
    tooltip=folium.GeoJsonTooltip(fields=["idse_new","pop_se","pop_se_ct"])
).add_to(m)

for _, r in points_gdf.iterrows():
    folium.CircleMarker(
        [r.geometry.y, r.geometry.x],
        radius=3,
        color="red",
        fill=True,
        fill_opacity=0.8
    ).add_to(m)

Draw(export=True).add_to(m)
MeasureControl().add_to(m)
MousePosition(prefix="Coordinates:").add_to(m)
folium.LayerControl(collapsed=True).add_to(m)

# =========================================================
# ✅ DYNAMIC LEGEND (OPEN / CLOSE)
# =========================================================
if show_legend:
    legend = MacroElement()
    legend._template = Template("""
    {% macro html(this, kwargs) %}
    <div style="
        position: fixed;
        bottom: 30px;
        left: 30px;
        z-index:9999;
        background-color: white;
        padding: 10px;
        border: 2px solid grey;
        border-radius: 6px;
        font-size: 13px;
    ">
        <b>🧭 Map Legend</b><br>
        <i style="background:blue;width:10px;height:10px;display:inline-block"></i>
        SE Polygon<br>
        <i style="background:red;width:10px;height:10px;display:inline-block"></i>
        Concession Point
    </div>
    {% endmacro %}
    """)
    m.get_root().add_child(legend)

# =========================================================
# LAYOUT
# =========================================================
col_map, col_chart = st.columns((3,1), gap="small")

with col_map:
    st_folium(m, height=500, use_container_width=True)

with col_chart:
    st.subheader("📊 Population (SE)")
    if idse_selected != "No filter":
        df_long = gdf_idse[["idse_new","pop_se","pop_se_ct"]].melt(
            id_vars="idse_new",
            var_name="Type",
            value_name="Population"
        )
        st.altair_chart(
            alt.Chart(df_long).mark_bar().encode(
                x="idse_new:N",
                y="Population:Q",
                color="Type:N"
            ),
            use_container_width=True
        )
# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping**  
**Dr. CAMARA MOC, PhD – Geomatics Engineering** © 2025
""")
