import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw, MousePosition
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
from shapely.geometry import shape, Point
import uuid
import json

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(layout="wide", page_title="Geospatial Enterprise Solution")
st.title("🌍 Geospatial Enterprise Solution")

# =========================================================
# SESSION STATE INIT
# =========================================================
for key in [
    "auth_ok", "username", "user_role",
    "points_gdf", "drawings_df"
]:
    if key not in st.session_state:
        st.session_state[key] = None

if st.session_state.drawings_df is None:
    st.session_state.drawings_df = pd.DataFrame(
        columns=["id", "type", "label", "geometry"]
    )

# =========================================================
# USERS
# =========================================================
USERS = {
    "admin": {"password": "admin2025", "role": "Admin"},
    "customer": {"password": "cust2025", "role": "Customer"},
}

# =========================================================
# LOGIN
# =========================================================
def logout():
    for k in st.session_state.keys():
        st.session_state[k] = None
    st.rerun()

if not st.session_state.auth_ok:
    st.sidebar.header("🔐 Login")
    u = st.sidebar.selectbox("User", USERS.keys())
    p = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if p == USERS[u]["password"]:
            st.session_state.auth_ok = True
            st.session_state.username = u
            st.session_state.user_role = USERS[u]["role"]
            st.rerun()
        else:
            st.sidebar.error("Wrong password")
    st.stop()

# =========================================================
# LOAD DATA
# =========================================================
SE_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/SE.geojson"
POINTS_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/concession.csv"

@st.cache_data
def load_se():
    g = gpd.read_file(SE_URL).to_crs(4326)
    g.columns = g.columns.str.lower()
    return g

@st.cache_data
def load_points():
    df = pd.read_csv(POINTS_URL)
    df = df.dropna(subset=["LAT", "LON"])
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.LON, df.LAT),
        crs=4326
    )

gdf = load_se()
points_gdf = load_points()

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown(f"**User:** {st.session_state.username}")
    if st.button("Logout"):
        logout()

# =========================================================
# MAP
# =========================================================
m = folium.Map(location=[13.5, -7.9], zoom_start=12)
folium.TileLayer("OpenStreetMap").add_to(m)

folium.GeoJson(
    gdf,
    style_function=lambda x: {"color": "blue", "weight": 1},
).add_to(m)

for _, r in points_gdf.iterrows():
    folium.CircleMarker(
        [r.geometry.y, r.geometry.x],
        radius=3, color="red", fill=True
    ).add_to(m)

Draw(
    export=False,
    draw_options={"polyline": False, "rectangle": False, "circle": False}
).add_to(m)

MeasureControl().add_to(m)
MousePosition().add_to(m)

# =========================================================
# DISPLAY MAP
# =========================================================
map_data = st_folium(m, height=520, returned_objects=["all_drawings"])

# =========================================================
# PROCESS DRAWINGS
# =========================================================
if map_data and map_data.get("all_drawings"):
    for f in map_data["all_drawings"]:
        geom = shape(f["geometry"])
        geom_id = str(uuid.uuid4())

        if geom.wkt in st.session_state.drawings_df.geometry.values:
            continue

        st.session_state.drawings_df.loc[len(st.session_state.drawings_df)] = [
            geom_id,
            f["geometry"]["type"],
            "",
            geom.wkt
        ]

# =========================================================
# EDITABLE DRAWINGS TABLE
# =========================================================
st.subheader("✏️ Drawings (Editable)")

edited = st.data_editor(
    st.session_state.drawings_df,
    num_rows="dynamic",
    use_container_width=True
)

st.session_state.drawings_df = edited

# =========================================================
# RELATION: MARKERS ↔ POLYGONS
# =========================================================
st.subheader("🔗 Marker–Polygon Relations")

polygons = edited[edited.type == "Polygon"]
markers = edited[edited.type == "Point"]

relations = []

for _, mrow in markers.iterrows():
    mp = shape({"type": "Point", "coordinates": json.loads(
        mrow.geometry.replace("POINT", "").replace("(", "[").replace(")", "]")
    )})
    for _, prow in polygons.iterrows():
        poly = shape({"type": "Polygon", "coordinates": json.loads(
            prow.geometry.replace("POLYGON", "").replace("(", "[").replace(")", "]")
        )})
        if poly.contains(mp):
            relations.append({
                "marker_id": mrow.id,
                "marker_label": mrow.label,
                "polygon_id": prow.id,
                "polygon_label": prow.label
            })

if relations:
    st.dataframe(pd.DataFrame(relations), use_container_width=True)
else:
    st.info("No marker inside polygons yet.")

# =========================================================
# EXPORT GEOJSON
# =========================================================
st.subheader("💾 Export Drawings")

if not edited.empty:
    features = []
    for _, r in edited.iterrows():
        features.append({
            "type": "Feature",
            "properties": {
                "id": r.id,
                "label": r.label,
                "type": r.type
            },
            "geometry": json.loads(gpd.GeoSeries.from_wkt([r.geometry]).__geo_interface__["features"][0]["geometry"])
        })

    geojson = json.dumps({
        "type": "FeatureCollection",
        "features": features
    })

    st.download_button(
        "⬇️ Download GeoJSON",
        geojson,
        "drawings.geojson",
        "application/geo+json"
    )

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping**  
**Dr. CAMARA MOC, PhD – Geomatics Engineering** © 2025
""")
