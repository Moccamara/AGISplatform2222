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
    st.session_state.clear()
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
    gdf = gpd.read_file(url).to_crs(4326)
    gdf.columns = gdf.columns.str.lower().str.strip()
    gdf = gdf.rename(columns={"lregion":"region","lcercle":"cercle","lcommune":"commune"})
    gdf = gdf[gdf.is_valid & ~gdf.is_empty]
    for c in ["region","cercle","commune","idse_new"]:
        if c not in gdf.columns:
            gdf[c] = ""
    for c in ["pop_se","pop_se_ct"]:
        if c not in gdf.columns:
            gdf[c] = 0
    return gdf

gdf = load_se_data(SE_URL)

# =========================================================
# LOAD POINTS
# =========================================================
POINTS_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/concession.csv"

@st.cache_data(show_spinner=False)
def load_points(url):
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
    st.session_state.points_gdf = load_points(POINTS_URL)

points_gdf = st.session_state.points_gdf

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown(f"**👤 User:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

    region = st.selectbox("Region", sorted(gdf["region"].unique()))
    gdf_r = gdf[gdf["region"] == region]

    cercle = st.selectbox("Cercle", sorted(gdf_r["cercle"].unique()))
    gdf_c = gdf_r[gdf_r["cercle"] == cercle]

    commune = st.selectbox("Commune", sorted(gdf_c["commune"].unique()))
    gdf_commune = gdf_c[gdf_c["commune"] == commune]

    idse_list = ["No filter"] + sorted(gdf_commune["idse_new"].unique())
    idse_selected = st.selectbox("Unit_Geo", idse_list)
    gdf_idse = gdf_commune if idse_selected=="No filter" else gdf_commune[gdf_commune["idse_new"]==idse_selected]

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(location=[(miny+maxy)/2,(minx+maxx)/2], zoom_start=18)

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
# ✅ TRUE DYNAMIC LEGEND (JS TOGGLE)
# =========================================================
legend = MacroElement()
legend._template = Template("""
{% macro html(this, kwargs) %}
<style>
#legendBox {
    position: fixed;
    bottom: 30px;
    left: 30px;
    z-index:9999;
    background:white;
    padding:10px;
    border:2px solid grey;
    border-radius:6px;
    display:none;
}
#legendBtn {
    position: fixed;
    bottom: 30px;
    left: 30px;
    z-index:10000;
    background:#2c7be5;
    color:white;
    padding:6px 10px;
    border-radius:4px;
    cursor:pointer;
    font-size:13px;
}
</style>

<div id="legendBtn" onclick="
var box=document.getElementById('legendBox');
box.style.display = (box.style.display==='none') ? 'block' : 'none';
">
☰ Legend
</div>

<div id="legendBox">
<b>🧭 Map Legend</b><br>
<span style="background:blue;width:10px;height:10px;display:inline-block"></span> SE Polygon<br>
<span style="background:red;width:10px;height:10px;display:inline-block"></span> Concession Point
</div>
{% endmacro %}
""")
m.get_root().add_child(legend)

# =========================================================
# DISPLAY
# =========================================================
st_folium(m, height=500, use_container_width=True)

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping**  
**Dr. CAMARA MOC, PhD – Geomatics Engineering** © 2025
""")
