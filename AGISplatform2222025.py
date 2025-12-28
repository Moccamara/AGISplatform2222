import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw
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

# =========================================================
# LOGOUT
# =========================================================
def logout():
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None
    st.experimental_rerun()

# =========================================================
# LOGIN
# =========================================================
if not st.session_state.auth_ok:
    st.sidebar.header("🔐 Login")
    username = st.sidebar.selectbox("User", list(USERS.keys()))
    password = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if password == USERS[username]["password"]:
            st.session_state.auth_ok = True
            st.session_state.username = username
            st.session_state.user_role = USERS[username]["role"]
            st.stop()
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
    gdf = gdf.set_crs(epsg=4326) if gdf.crs is None else gdf.to_crs(epsg=4326)
    gdf.columns = gdf.columns.str.lower().str.strip()
    gdf = gdf.rename(columns={"lregion": "region", "lcercle": "cercle", "lcommune": "commune"})
    gdf = gdf[gdf.is_valid & ~gdf.is_empty]
    for col in ["region", "cercle", "commune", "idse_new"]:
        if col not in gdf.columns:
            gdf[col] = ""
    for col in ["pop_se", "pop_se_ct"]:
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
    df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["LON"] = pd.to_numeric(df["LON"], errors="coerce")
    df = df.dropna(subset=["LAT", "LON"])
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["LON"], df["LAT"]), crs="EPSG:4326")

points_gdf = load_points(POINTS_URL)
st.session_state.points_gdf = points_gdf

# =========================================================
# SAFE SPATIAL JOIN
# =========================================================
def safe_sjoin(points, polygons):
    if points is None or polygons is None or points.empty or polygons.empty:
        return gpd.GeoDataFrame()
    return gpd.sjoin(points, polygons, predicate="intersects")

# =========================================================
# SIDEBAR FILTERS
# =========================================================
with st.sidebar:
    st.markdown(f"**Logged in as:** {st.session_state.username}")
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
    gdf_idse = gdf_commune if idse_selected == "No filter" else gdf_commune[gdf_commune["idse_new"] == idse_selected]

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_idse.total_bounds
m = folium.Map(location=[(miny + maxy) / 2, (minx + maxx) / 2], zoom_start=18)
folium.GeoJson(gdf_idse).add_to(m)
MeasureControl().add_to(m)
Draw(export=True).add_to(m)

# =========================================================
# LAYOUT
# =========================================================
col_map, col_chart = st.columns((3, 1), gap="small")

with col_map:
    map_data = st_folium(m, height=500, returned_objects=["all_drawings"])

    # ===== DRAWN POLYGON STATISTICS (TEXT ONLY) =====
    if map_data and map_data.get("all_drawings"):
        last_feature = map_data["all_drawings"][-1]
        if "geometry" in last_feature:
            polygon = shape(last_feature["geometry"])
            pts = points_gdf[points_gdf.geometry.within(polygon)]

            st.subheader("🟢 Drawn polygon statistics")

            if pts.empty:
                st.info("No points inside drawn polygon.")
            else:
                m_poly = int(pd.to_numeric(pts.get("Masculin"), errors="coerce").fillna(0).sum())
                f_poly = int(pd.to_numeric(pts.get("Feminin"), errors="coerce").fillna(0).sum())

                st.markdown(
                    f"""
                    - 👨 **Masculin**: {m_poly}
                    - 👩 **Feminin**: {f_poly}
                    - 👥 **Total**: {m_poly + f_poly}
                    """
                )

# =========================================================
# RIGHT PANEL — SE CHARTS (UNCHANGED)
# =========================================================
with col_chart:
    if idse_selected == "No filter":
        st.info("Select SE.")
    else:
        st.subheader("📊 Population")
        df_long = gdf_idse.melt(
            id_vars="idse_new",
            value_vars=["pop_se", "pop_se_ct"],
            var_name="Type",
            value_name="Population",
        )
        st.altair_chart(
            alt.Chart(df_long)
            .mark_bar()
            .encode(x="idse_new:N", y="Population:Q", color="Type:N"),
            use_container_width=True,
        )

        st.subheader("👥 Sex (M / F)")
        pts_inside = safe_sjoin(points_gdf, gdf_idse.explode())
        m_total = int(pts_inside["Masculin"].sum()) if not pts_inside.empty else 0
        f_total = int(pts_inside["Feminin"].sum()) if not pts_inside.empty else 0
        st.markdown(f"- 👨 **M**: {m_total}\n- 👩 **F**: {f_total}\n- 👥 **Total**: {m_total+f_total}")

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping**  
**Dr. MOC CAMARA, PhD – Geomatics Engineering** © 2025
""")
