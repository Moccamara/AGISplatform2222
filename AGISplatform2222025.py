import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw, MousePosition
import pandas as pd
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
    st.session_state.markers_df = pd.DataFrame(columns=["Latitude","Longitude","Label"])
    st.session_state.polygons_df = pd.DataFrame(columns=["Polygon #","Total Points","Label"])

# =========================================================
# LOGOUT
# =========================================================
def logout():
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None
    st.session_state.markers_df = pd.DataFrame(columns=["Latitude","Longitude","Label"])
    st.session_state.polygons_df = pd.DataFrame(columns=["Polygon #","Total Points","Label"])
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

try:
    gdf = load_se_data(SE_URL)
except Exception:
    st.error("❌ Unable to load SE.geojson from GitHub")
    st.stop()

# =========================================================
# LOAD CONCESSION POINTS
# =========================================================
POINTS_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/concession.csv"

@st.cache_data(show_spinner=False)
def load_points_from_github(url):
    try:
        df = pd.read_csv(url)
        if not {"LAT", "LON"}.issubset(df.columns):
            return None
        df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
        df["LON"] = pd.to_numeric(df["LON"], errors="coerce")
        df = df.dropna(subset=["LAT","LON"])
        return gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["LON"], df["LAT"]),
            crs="EPSG:4326"
        )
    except:
        return None

# =========================================================
# POINTS SOURCE LOGIC
# =========================================================
if st.session_state.points_gdf is not None:
    points_gdf = st.session_state.points_gdf
else:
    points_gdf = load_points_from_github(POINTS_URL)
    st.session_state.points_gdf = points_gdf

# =========================================================
# SAFE SPATIAL JOIN
# =========================================================
def safe_sjoin(points, polygons, how="inner", predicate="intersects"):
    if points is None or points.empty or polygons is None or polygons.empty:
        return gpd.GeoDataFrame(
            columns=points.columns if points is not None else [],
            crs=points.crs if points is not None else None
        )
    for col in ["index_right", "_r"]:
        if col in polygons.columns:
            polygons = polygons.drop(columns=[col])
    return gpd.sjoin(points, polygons, how=how, predicate=predicate, rsuffix="_r")

# =========================================================
# SIDEBAR FILTERS
# =========================================================
with st.sidebar:
    st.image("logo/logo_wgv.png", width=200)
    st.markdown(f"**Logged in as:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

    st.markdown("### 🗂️ Attribute Query")
    region = st.selectbox("Region", sorted(gdf["region"].dropna().unique()))
    gdf_r = gdf[gdf["region"] == region]

    cercle = st.selectbox("Cercle", sorted(gdf_r["cercle"].dropna().unique()))
    gdf_c = gdf_r[gdf_r["cercle"] == cercle]

    commune = st.selectbox("Commune", sorted(gdf_c["commune"].dropna().unique()))
    gdf_commune = gdf_c[gdf_c["commune"] == commune]

    idse_list = ["No filter"] + sorted(gdf_commune["idse_new"].dropna().unique())
    idse_selected = st.selectbox("Unit_Geo", idse_list)
    gdf_idse = gdf_commune if idse_selected=="No filter" else gdf_commune[gdf_commune["idse_new"]==idse_selected]

# =========================================================
# MAP SETUP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(location=[(miny+maxy)/2, (minx+maxx)/2], zoom_start=18)

# Base layers
folium.TileLayer("OpenStreetMap").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satellite",
    attr="Esri",
    control=True
).add_to(m)

m.fit_bounds([[miny,minx],[maxy,maxx]])

# Overlay layers
fg_idse = folium.FeatureGroup(name="SE Polygons", show=True)
folium.GeoJson(
    gdf_idse,
    style_function=lambda x: {"color":"blue","weight":2,"fillOpacity":0.15},
    tooltip=folium.GeoJsonTooltip(fields=["idse_new","pop_se","pop_se_ct"])
).add_to(fg_idse)
fg_idse.add_to(m)

# Concession Points
points_to_plot = points_gdf
fg_points = folium.FeatureGroup(name="Concession Points", show=True)
if points_to_plot is not None:
    points_to_plot = points_to_plot.to_crs(gdf_idse.crs)
    for _, r in points_to_plot.iterrows():
        folium.CircleMarker(
            location=[r.geometry.y, r.geometry.x],
            radius=3,
            color="red",
            fill=True,
            fill_opacity=0.8
        ).add_to(fg_points)
fg_points.add_to(m)

# Plugins
MeasureControl().add_to(m)
draw_control = Draw(export=True, draw_options={"polyline": False, "rectangle": False, "circle": False, "circlemarker": False})
draw_control.add_to(m)

MousePosition(
    position="bottomright",
    separator=" | ",
    empty_string="Move cursor",
    lng_first=True,
    num_digits=6,
    prefix="Coordinates:"
).add_to(m)

folium.LayerControl(collapsed=True).add_to(m)

# =========================================================
# LAYOUT
# =========================================================
col_map, col_chart = st.columns((3,1), gap="small")
with col_map:
    map_data = st_folium(
        m,
        height=600,
        returned_objects=["all_drawings"],
        use_container_width=True
    )

    # ================================
    # HANDLE MARKERS
    # ================================
    if map_data and "all_drawings" in map_data:
        for feature in map_data["all_drawings"]:
            if feature["geometry"]["type"] == "Point":
                geom = shape(feature["geometry"])
                # Add new marker if not exists
                if not ((st.session_state.markers_df["Latitude"]==geom.y) & 
                        (st.session_state.markers_df["Longitude"]==geom.x)).any():
                    st.session_state.markers_df = pd.concat([
                        st.session_state.markers_df,
                        pd.DataFrame({"Latitude":[geom.y], "Longitude":[geom.x], "Label":[""]})
                    ], ignore_index=True)

    st.subheader("📍 Drawn Markers Coordinates (Dynamic Table)")
    markers_edited = st.data_editor(st.session_state.markers_df, num_rows="dynamic")
    st.session_state.markers_df = markers_edited

    csv = st.session_state.markers_df.to_csv(index=False)
    st.download_button("📥 Download Marker CSV", csv, "markers.csv", "text/csv")

    # ================================
    # HANDLE POLYGONS
    # ================================
    if map_data and "all_drawings" in map_data:
        polygon_counter = len(st.session_state.polygons_df) + 1
        for feature in map_data["all_drawings"]:
            if feature["geometry"]["type"] in ["Polygon","MultiPolygon"]:
                geom = shape(feature["geometry"])
                # Check if polygon already exists
                exists = st.session_state.polygons_df["Polygon #"].isin([feature["properties"].get("id",polygon_counter)])
                if not exists.any():
                    # Count points inside polygon
                    total_pts = len(points_gdf[points_gdf.geometry.within(geom)])
                    st.session_state.polygons_df = pd.concat([
                        st.session_state.polygons_df,
                        pd.DataFrame({
                            "Polygon #":[polygon_counter],
                            "Total Points":[total_pts],
                            "Label":[""]
                        })
                    ], ignore_index=True)
                    polygon_counter += 1

    st.subheader("🟢 Points inside drawn polygons")
    polygons_edited = st.data_editor(st.session_state.polygons_df, num_rows="dynamic")
    st.session_state.polygons_df = polygons_edited

with col_chart:
    st.subheader("📊 Population per SE")
    if idse_selected=="No filter":
        st.info("Select SE to view population charts")
    else:
        df_long = gdf_idse[["idse_new","pop_se","pop_se_ct"]].copy()
        df_long = df_long.melt(id_vars="idse_new", value_vars=["pop_se","pop_se_ct"],
                               var_name="Variable", value_name="Population")
        df_long["Variable"] = df_long["Variable"].replace({"pop_se":"Pop Ref","pop_se_ct":"Pop Current"})
        st.bar_chart(df_long.set_index("idse_new")["Population"])

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping** Developed with Streamlit, Folium & GeoPandas  
**Dr. CAMARA MOC, PhD – Geomatics Engineering** © 2025
""")
