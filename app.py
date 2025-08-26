import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import MarkerCluster, FastMarkerCluster
from streamlit_folium import st_folium
import os

# =========================
# 🔧 EDIT THESE PATHS
# =========================
PATH_STORE_CSV   = "Gerzeny_store.csv"  # URL Data (Green)
PATH_URL_CSV = "Spoutro August 2025 1(in).csv"              # Store Data (Blue)

# ---------------- Page config & style ----------------
st.set_page_config(page_title="Gerzeny's Data — URL (Green) & Store (Blue)", page_icon="🌍", layout="wide")
st.markdown("""
<style>
.main-header{font-size:2.0rem;color:#1f77b4;text-align:center;margin:.25rem 0 .75rem;}
.cluster-popup{font-family:Arial, sans-serif;font-size:12px;line-height:1.25;padding:5px;max-width:320px;}
.block-container{padding-top: 0.8rem;}
.path-note{font-size:12px;color:#666;}
</style>
""", unsafe_allow_html=True)

# ---------------- Helpers ----------------
def validate_coordinates(lat, lon):
    try:
        lat = float(lat); lon = float(lon)
        return (-90 <= lat <= 90) and (-180 <= lon <= 180)
    except Exception:
        return False

@st.cache_data(show_spinner=False)
def parse_csv(path_or_buf):
    """Read a CSV and return (valid_df, valid_count, invalid_count, postal_col, name_col, lat_col, lon_col)."""
    df = pd.read_csv(path_or_buf)

    # Detect lat/lon columns
    lat_col = lon_col = None
    for c in df.columns:
        lc = c.lower()
        if lat_col is None and any(t in lc for t in ["lat","latitude"]): lat_col = c
        if lon_col is None and any(t in lc for t in ["lon","long","longitude","lng"]): lon_col = c
    if lat_col is None or lon_col is None:
        nums = df.select_dtypes(include=[np.number]).columns.tolist()
        if len(nums) >= 2:
            lat_col, lon_col = nums[:2]
        else:
            return pd.DataFrame(), 0, len(df), None, None, None, None

    # Coerce & validate
    tmp = df.copy()
    tmp["__lat"] = pd.to_numeric(tmp[lat_col], errors="coerce")
    tmp["__lon"] = pd.to_numeric(tmp[lon_col], errors="coerce")
    mask = (
        tmp["__lat"].notna() & tmp["__lon"].notna()
        & tmp["__lat"].between(-90, 90) & tmp["__lon"].between(-180, 180)
    )
    valid = tmp.loc[mask].copy()
    valid.rename(columns={"__lat":"latitude","__lon":"longitude"}, inplace=True)
    valid.drop(columns=["__lat","__lon"], inplace=True, errors="ignore")

    # Detect postal & name columns
    postal_candidates = [c for c in valid.columns if any(t in c.lower()
                         for t in ["postal","postal code","zip","zip code","zipcode","post_code","pincode","zip_code"])]
    postal_col = postal_candidates[0] if postal_candidates else None
    name_candidates = [c for c in valid.columns if c.lower() in ["name","title","label","location_name"]]
    name_col = name_candidates[0] if name_candidates else None

    return valid, int(mask.sum()), int(len(df) - mask.sum()), postal_col, name_col, lat_col, lon_col

def popup_html(row, postal_col=None, name_col=None):
    parts = ["<div class='cluster-popup'>", "<b>📍 Location Details</b><br>"]
    if name_col and name_col in row and pd.notna(row[name_col]):
        parts.append(f"<b>Name:</b> {row[name_col]}<br>")
    parts.append(f"<b>Latitude:</b> {row['Latitude']:.6f}<br>")
    parts.append(f"<b>Longitude:</b> {row['Longitude']:.6f}<br>")
    if postal_col and postal_col in row and pd.notna(row[postal_col]):
        parts.append(f"<b>Postal Code:</b> {row[postal_col]}<br>")
    if "state" in row and pd.notna(row["state"]):   parts.append(f"<b>State:</b> {row['state']}<br>")
    if "city"  in row and pd.notna(row["city"]):    parts.append(f"<b>City:</b> {row['city']}<br>")
    if "address" in row and pd.notna(row["address"]): parts.append(f"<b>Address:</b> {row['address']}<br>")
    parts.append("</div>")
    return "".join(parts)

def tooltip_html(row, postal_col=None, name_col=None):
    """Tooltip with exact labels: Latitude, Longitude, Postal Code."""
    name_line = ""
    if name_col and name_col in row and pd.notna(row[name_col]):
        name_line = f"<b>{row[name_col]}</b><br>"
    lat_val = row.get("latitude", None)
    lon_val = row.get("longitude", None)
    latlon_line = "Latitude: n/a, Longitude: n/a"
    if lat_val is not None and lon_val is not None:
        latlon_line = f"Latitude: {float(lat_val):.6f}, Longitude: {float(lon_val):.6f}"
    postal_line = ""
    if postal_col and postal_col in row and pd.notna(row[postal_col]):
        postal_line = f"<br>Postal Code: {row[postal_col]}"
    return f"{name_line}{latlon_line}{postal_line}"

def add_layer(df, color, layer_name, cluster=True, fast=False, postal_col=None, name_col=None):
    """
    fast=True -> FastMarkerCluster (very fast, but no custom icon/popup/tooltip on spiderfy).
    fast=False -> MarkerCluster with colored house icons + popups/tooltips.
    """
    layer = folium.FeatureGroup(name=layer_name, overlay=True, control=True)
    if df.empty:
        return layer

    if cluster and fast:
        pts = df[["latitude","longitude"]].to_numpy().tolist()
        FastMarkerCluster(pts, name=f"{layer_name} Fast").add_to(layer)
        return layer

    cl = MarkerCluster(
        name=f"{layer_name} Clusters", overlay=True, control=False,
        options={'maxClusterRadius':50,'spiderfyOnMaxZoom':True,'showCoverageOnHover':True,'zoomToBoundsOnClick':True}
    )
    layer.add_child(cl)
    for _, r in df.iterrows():
        folium.Marker(
            [r["latitude"], r["longitude"]],
            tooltip=folium.Tooltip(tooltip_html(r, postal_col, name_col), sticky=True, direction="top"),
            popup=folium.Popup(popup_html(r, postal_col, name_col), max_width=320),
            icon=folium.Icon(color=color, icon="home", prefix="fa")
        ).add_to(cl)
    return layer

def build_map(url_df, store_df, cluster=True, fast_csv=False,
              postal1=None, postal2=None, name1=None, name2=None):
    if url_df.empty and store_df.empty:
        return folium.Map(location=[20,0], zoom_start=2)
    base = pd.concat(
        [url_df[["latitude","longitude"]]] if not url_df.empty else [] +
        [store_df[["latitude","longitude"]]] if not store_df.empty else [],
        ignore_index=True
    )
    m = folium.Map(location=[base["latitude"].mean(), base["longitude"].mean()], zoom_start=9)

    # URL Data = GREEN, Store Data = BLUE
    add_layer(url_df,   "green", "URL Data (Green)",  cluster, fast_csv, postal1, name1).add_to(m)
    add_layer(store_df, "blue",  "Store Data (Blue)", cluster, fast_csv, postal2, name2).add_to(m)

    folium.plugins.Fullscreen(position='topright').add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m

# ---------------- App ----------------
def main():
    st.markdown('<h1 class="main-header">🌍 Gerzeny\'s Data — URL (Green) & Store (Blue)</h1>', unsafe_allow_html=True)

    # st.markdown(
    #     f"<div class='path-note'>"
    #     f"<b>URL Data path:</b> {PATH_URL_CSV}<br>"
    #     f"<b>Store Data path:</b> {PATH_STORE_CSV}"
    #     f"</div>", unsafe_allow_html=True
    # )

    with st.sidebar:
        st.header("⚙️ Map Settings")
        cluster = st.checkbox("Cluster locations", value=True)
        fast_csv = st.checkbox(
            "High-speed for large CSVs (FastMarkerCluster)",
            value=False,
            help="Faster for big files. Disables per-point tooltips/popups (Leaflet limitation)."
        )

    # Load CSVs directly from paths
    url_df  = pd.DataFrame()
    store_df = pd.DataFrame()
    url_ok = url_bad = st_ok = st_bad = 0
    postal1 = postal2 = name1 = name2 = None

    if PATH_URL_CSV and os.path.exists(PATH_URL_CSV):
        url_df, url_ok, url_bad, postal1, name1, _, _ = parse_csv(PATH_URL_CSV)
    else:
        st.warning(f"URL Data file not found at: {PATH_URL_CSV}")

    if PATH_STORE_CSV and os.path.exists(PATH_STORE_CSV):
        store_df, st_ok, st_bad, postal2, name2, _, _ = parse_csv(PATH_STORE_CSV)
    else:
        st.warning(f"Store Data file not found at: {PATH_STORE_CSV}")

    # Metrics
    total = len(url_df) + len(store_df)
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Total Locations", f"{total:,}")
    with c2:
        if total:
            lat_all = pd.concat([s for s in [url_df.get("latitude"), store_df.get("latitude")] if s is not None], ignore_index=True)
            st.metric("Avg Latitude", f"{lat_all.mean():.6f}")
        else: st.metric("Avg Latitude", "—")
    with c3:
        if total:
            lon_all = pd.concat([s for s in [url_df.get("longitude"), store_df.get("longitude")] if s is not None], ignore_index=True)
            st.metric("Avg Longitude", f"{lon_all.mean():.6f}")
        else: st.metric("Avg Longitude", "—")
    with c4:
        any_postal = postal1 or postal2
        if any_postal:
            series_list = []
            if postal1 and postal1 in url_df.columns:   series_list.append(url_df[postal1])
            if postal2 and postal2 in store_df.columns: series_list.append(store_df[postal2])
            if series_list:
                st.metric("Unique Postal Codes", pd.concat(series_list, ignore_index=True).nunique(dropna=True))
            else:
                st.metric("Unique Postal Codes", "0")
        else:
            st.metric("Unique Postal Codes", "Not found")

    # Map (full width)
    st.markdown("### 📍 Locations")
    with st.spinner("Rendering map..."):
        fmap = build_map(
            url_df, store_df, cluster=cluster, fast_csv=fast_csv,
            postal1=postal1, postal2=postal2, name1=name1, name2=name2
        )
    st_folium(fmap, width=None, height=640, returned_objects=[])

    # Postal Code summary (bar graph)
    st.markdown("### 🧭 Postal Code Summary")
    if postal1 or postal2:
        series = []
        if postal1 and postal1 in url_df.columns:     series.append(url_df[postal1].dropna().astype(str))
        if postal2 and postal2 in store_df.columns:   series.append(store_df[postal2].dropna().astype(str))
        if series:
            combined = pd.concat(series, ignore_index=True)
            counts = combined.value_counts().head(20)
            st.bar_chart(counts)
        else:
            st.info("No postal codes detected in the provided CSVs.")
    else:
        st.info("No postal code column detected. Use a column like 'postal', 'zip', 'zipcode', 'post_code', or 'pincode'.")

    # Data previews
    with st.expander("📊 URL Data (valid rows)"):
        if not url_df.empty:
            st.write(f"✅ Valid: {url_ok:,} | ❌ Invalid: {url_bad:,}")
            st.dataframe(url_df.head(25), use_container_width=True)
        else:
            st.info("No valid rows in URL Data.")
    with st.expander("📊 Store Data (valid rows)"):
        if not store_df.empty:
            st.write(f"✅ Valid: {st_ok:,} | ❌ Invalid: {st_bad:,}")
            st.dataframe(store_df.head(25), use_container_width=True)
        else:
            st.info("No valid rows in Store Data.")

if __name__ == "__main__":
    main()
