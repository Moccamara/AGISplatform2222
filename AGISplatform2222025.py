import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw, MousePosition
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
from shapely.geometry import shape

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

if "markers_list" not in st.session_state:
    st.session_state.markers_list = []

if "polygons_list" not in st.session_state:
    st.session_state.polygons_list = []

if "pts_inside_map" not in st.session_state:
    st.session_state.pts_inside_map = None

# =========================================================
# LOGOUT
# =========================================================
def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
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
    gdf = gpd.read_file(url).to_crs(epsg=4326)
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
def load_points(url):
    df = pd.read_csv(url)
    df = df.dropna(subset=["LAT","LON"])
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["LON"], df["LAT"]),
        crs="EPSG:4326"
    )

points_gdf = load_points(POINTS_URL)

# =========================================================
# SAFE SPATIAL JOIN
# =========================================================
def safe_sjoin(points, polygons, predicate="intersects"):
    if points is None or polygons is None or points.empty or polygons.empty:
        return gpd.GeoDataFrame(columns=points.columns, crs=points.crs)
    return gpd.sjoin(points, polygons, predicate=predicate)

# =========================================================
# SIDEBAR FILTERS
# =========================================================
with st.sidebar:
    st.markdown(f"**User:** {st.session_state.username} ({st.session_state.user_role})")

    region = st.selectbox("Region", sorted(gdf["region"].unique()))
    gdf_r = gdf[gdf["region"] == region]

    cercle = st.selectbox("Cercle", sorted(gdf_r["cercle"].unique()))
    gdf_c = gdf_r[gdf_r["cercle"] == cercle]

    commune = st.selectbox("Commune", sorted(gdf_c["commune"].unique()))
    gdf_commune = gdf_c[gdf_c["commune"] == commune]

    idse_selected = st.selectbox("Unit_Geo", ["No filter"] + sorted(gdf_commune["idse_new"].unique()))
    gdf_idse = gdf_commune if idse_selected == "No filter" else gdf_commune[gdf_commune["idse_new"] == idse_selected]

    # ---------------- Admin spatial query
    if st.session_state.user_role == "Admin":
        st.markdown("### 🛰️ Spatial Query")
        if st.button("Run Spatial Query"):
            st.session_state.pts_inside_map = safe_sjoin(points_gdf, gdf_idse)
            st.success(f"{len(st.session_state.pts_inside_map)} points found")

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(location=[(miny+maxy)/2, (minx+maxx)/2], zoom_start=18)

folium.TileLayer("OpenStreetMap").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satellite",
    attr="Esri"
).add_to(m)

folium.GeoJson(
    gdf_idse,
    name="SE Polygons",
    style_function=lambda x: {"color":"blue","fillOpacity":0.15}
).add_to(m)

pts_to_plot = st.session_state.pts_inside_map if st.session_state.pts_inside_map is not None else points_gdf
for _, r in pts_to_plot.iterrows():
    folium.CircleMarker([r.geometry.y, r.geometry.x], radius=3, color="red").add_to(m)

Draw(
    draw_options={"polyline": False, "rectangle": False, "circle": False, "circlemarker": False}
).add_to(m)

MeasureControl().add_to(m)
MousePosition().add_to(m)
folium.LayerControl(collapsed=True).add_to(m)

# =========================================================
# LAYOUT
# =========================================================
col_map, col_chart = st.columns((3,1))

with col_map:
    map_data = st_folium(m, height=500, returned_objects=["all_drawings"])

    drawings = []
    if map_data:
        drawings = map_data.get("all_drawings", []) or []

    # -------- MARKERS
    for f in drawings:
        if f["geometry"]["type"] == "Point":
            p = shape(f["geometry"])
            coord = (p.y, p.x)
            if coord not in st.session_state.markers_list:
                st.session_state.markers_list.append(coord)

    if st.session_state.markers_list:
        df_markers = pd.DataFrame(st.session_state.markers_list, columns=["Lat","Lon"])
        df_markers["Label"] = ""
        st.subheader("📍 Drawn Markers")
        st.data_editor(df_markers, num_rows="dynamic", use_container_width=True)

    # -------- POLYGONS
    for f in drawings:
        if f["geometry"]["type"] == "Polygon":
            poly = shape(f["geometry"])
            if poly not in st.session_state.polygons_list:
                st.session_state.polygons_list.append(poly)

    if st.session_state.polygons_list:
        rows = []
        for i, poly in enumerate(st.session_state.polygons_list, 1):
            rows.append({
                "Polygon ID": i,
                "Label": "",
                "Total Points": len(points_gdf[points_gdf.geometry.within(poly)])
            })
        st.subheader("🟢 Polygons Statistics")
        st.data_editor(pd.DataFrame(rows), num_rows="dynamic", use_container_width=True)

with col_chart:
    st.subheader("📊 Population")
    if idse_selected != "No filter":
        df = gdf_idse[["idse_new","pop_se","pop_se_ct"]].melt(
            id_vars="idse_new", var_name="Type", value_name="Population"
        )
        st.altair_chart(
            alt.Chart(df).mark_bar().encode(
                x="idse_new:N", y="Population:Q", color="Type:N"
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
