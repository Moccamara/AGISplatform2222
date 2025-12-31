import streamlit as st
import geopandas as gpd
import folium
from folium.plugins import MeasureControl, Draw, MousePosition
from streamlit_folium import st_folium
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
from shapely.geometry import shape, Point, mapping
import json

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
    st.session_state.drawings = []

# =========================================================
# LOGOUT
# =========================================================
def logout():
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None
    st.session_state.drawings = []
    st.experimental_rerun()

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
            st.experimental_rerun()
        else:
            st.sidebar.error("❌ Incorrect password")
    st.stop()

# =========================================================
# LOAD SE POLYGONS
# =========================================================
SE_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/SE.geojson"

@st.cache_data
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

@st.cache_data
def load_points(url):
    df = pd.read_csv(url)
    df = df.dropna(subset=["LAT","LON"])
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.LON, df.LAT), crs="EPSG:4326")

if st.session_state.points_gdf is None:
    st.session_state.points_gdf = load_points(POINTS_URL)
points_gdf = st.session_state.points_gdf

# =========================================================
# SAFE SPATIAL JOIN
# =========================================================
def safe_sjoin(points, polygons, how="inner", predicate="intersects"):
    if points is None or points.empty or polygons is None or polygons.empty:
        return gpd.GeoDataFrame(columns=points.columns if points is not None else [], crs=points.crs if points is not None else None)
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
    # Spatial Query (Admin only)
    # =========================================================
    pts_inside_map = None
    if st.session_state.user_role=="Admin":
        st.markdown("### 🛰️ Spatial Query")
        run_query = st.button("Run Spatial Query")
        if run_query and points_gdf is not None:
            pts_inside_map = safe_sjoin(points_gdf, gdf_idse, predicate="intersects")
            st.success(f"✅ Spatial query returned {len(pts_inside_map)} points inside selected SE.")

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(location=[(miny+maxy)/2, (minx+maxx)/2], zoom_start=18)
folium.TileLayer("OpenStreetMap").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="Satellite",
    attr="Esri",
    control=True
).add_to(m)
m.fit_bounds([[miny,minx],[maxy,maxx]])

# ===== Overlay layers =====
fg_idse = folium.FeatureGroup(name="SE Polygons", show=True)
folium.GeoJson(
    gdf_idse,
    style_function=lambda x: {"color":"blue","weight":2,"fillOpacity":0.15},
    tooltip=folium.GeoJsonTooltip(fields=["idse_new","pop_se","pop_se_ct"])
).add_to(fg_idse)
fg_idse.add_to(m)

points_to_plot = pts_inside_map if pts_inside_map is not None else points_gdf
fg_points = folium.FeatureGroup(name="Concession Points", show=True)
if points_to_plot is not None:
    points_to_plot = points_to_plot.to_crs(gdf_idse.crs)
    for _, r in points_to_plot.iterrows():
        folium.CircleMarker(
            location=[r.geometry.y, r.geometry.x],
            radius=3, color="red", fill=True, fill_opacity=0.8,
            popup=f"{r.get('Nom','')} {r.get('ID','')}"
        ).add_to(fg_points)
fg_points.add_to(m)

MeasureControl().add_to(m)
draw_control = Draw(
    export=True,
    draw_options={"polyline": False, "rectangle": False, "circle": False, "circlemarker": False},
    edit_options={"edit": True}
)
draw_control.add_to(m)

MousePosition(
    position="bottomright", separator=" | ", empty_string="Move cursor",
    lng_first=True, num_digits=6, prefix="Coordinates:"
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

    # Save drawings to session
    if map_data and "all_drawings" in map_data and map_data["all_drawings"]:
        st.session_state.drawings = map_data["all_drawings"]

    # ================================
    # DRAWN MARKERS & POLYGONS
    # ================================
    markers_list = []
    polygons_list = []

    for feature in st.session_state.drawings:
        geom_type = feature["geometry"]["type"]
        geom_shape = shape(feature["geometry"])
        label = feature.get("properties", {}).get("label", "")
        if geom_type == "Point":
            markers_list.append({"lat": geom_shape.y, "lon": geom_shape.x, "label": label})
        elif geom_type in ["Polygon","MultiPolygon"]:
            polygons_list.append({"geometry": geom_shape, "label": label})

    if markers_list:
        markers_df = pd.DataFrame(markers_list)
        st.subheader("📍 Drawn Markers")
        st.dataframe(markers_df)

        csv = markers_df.to_csv(index=False)
        st.download_button("📥 Download Markers CSV", data=csv, file_name="markers.csv", mime="text/csv")

    if polygons_list:
        st.subheader("🔹 Drawn Polygons")
        polygons_geojson = [mapping(p["geometry"]) for p in polygons_list]
        st.json(polygons_geojson)

with col_chart:
    # Population chart
    if idse_selected != "No filter":
        st.subheader("📊 Population")
        df_long = gdf_idse[["idse_new","pop_se","pop_se_ct"]].copy()
        df_long = df_long.melt(id_vars="idse_new", value_vars=["pop_se","pop_se_ct"],
                               var_name="Variable", value_name="Population")
        df_long["Variable"] = df_long["Variable"].replace({"pop_se":"Pop Ref","pop_se_ct":"Pop Current"})
        chart = (alt.Chart(df_long)
                 .mark_bar()
                 .encode(x=alt.X("idse_new:N", title=None, axis=alt.Axis(labelAngle=0)),
                         xOffset="Variable:N",
                         y=alt.Y("Population:Q", title=None),
                         color=alt.Color("Variable:N", legend=alt.Legend(orient="right", title="Type")),
                         tooltip=["idse_new","Variable","Population"])
                 .properties(height=200))
        st.altair_chart(chart, use_container_width=True)

        # Sex pie chart
        st.subheader("👥 Sex (M / F)")
        if {"Masculin","Feminin"}.issubset(points_gdf.columns):
            gdf_idse_simple = gdf_idse.explode(ignore_index=True)
            pts_inside = safe_sjoin(points_gdf, gdf_idse_simple, predicate="intersects")
            m_total = int(pts_inside["Masculin"].sum()) if not pts_inside.empty else 0
            f_total = int(pts_inside["Feminin"].sum()) if not pts_inside.empty else 0
            st.markdown(f"- 👨 **M**: {m_total}  \n- 👩 **F**: {f_total}  \n- 👥 **Total**: {m_total+f_total}")

            fig, ax = plt.subplots(figsize=(3,3))
            if m_total + f_total > 0:
                ax.pie([m_total,f_total], labels=["M","F"], autopct="%1.1f%%", startangle=90, colors=["#1f77b4","#ff7f0e"])
            else:
                ax.pie([1], labels=["No data"], colors=["lightgrey"])
            ax.axis("equal")
            st.pyplot(fig)

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping** Developed with Streamlit, Folium & GeoPandas  
**Dr. CAMARA MOC, PhD – Geomatics Engineering** © 2025
""")
