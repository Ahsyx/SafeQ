import streamlit as st
import sys
import os
import folium
import osmnx as ox
from streamlit_folium import st_folium
import networkx as nx

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from engine import get_city_graph, inject_hazard, solve_safe_route, VEHICLE_PROFILES, AMBULANCE_PROFILES
from database import verify_vehicle

# --- PAGE CONFIG ---
st.set_page_config(page_title="SafeQ Global", layout="wide", page_icon="🛡️")

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #00ff88; color: black; font-weight: bold; }
    [data-testid="stMetric"] {
        background-color: #1e2130;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #333;
        min-height: 130px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    [data-testid="stMetricLabel"] { font-size: 1rem; color: #aaa; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- SESSION INITIALIZATION ---
defaults = {
    'logged_in': False,
    'G': None,
    'start': None,
    'end': None,
    'hazards': [],
    # FIX: store the city name so geocoding uses the correct context
    'city_query': "Kochi, Kerala, India"
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==========================================
# 🔐 LOGIN GATE
# ==========================================
if not st.session_state.logged_in:
    st.title("🛡️ SafeQ: Autonomous Safety Dashboard")
    user_in = st.text_input("Registration Number", placeholder="e.g. KL-07-AW-1234")
    if st.button("Verify & Sign In"):
        if user_in:
            v_type = verify_vehicle(user_in)
            st.session_state.user_data = {
                "reg_id": user_in.upper(),
                "type": v_type,
                "icon": VEHICLE_PROFILES[v_type]['icon']
            }
            st.session_state.logged_in = True
            st.rerun()
    st.stop()

# ==========================================
# 🗺️ MAIN APP
# ==========================================
risk_score = 0
dist_total = 0
path_safe  = []
safety_val = 0.0

with st.sidebar:
    st.title("🛡️ SafeQ Control")
    user = st.session_state.user_data
    st.success(f"ID: {user['reg_id']}")
    st.info(f"Priority: {user['icon']} {user['type']}")

    # --- AMBULANCE MODE SWITCHER ---
    if user['type'] in AMBULANCE_PROFILES:
        st.divider()
        st.markdown("### 🚑 Ambulance Mode")
        amb_mode = st.radio(
            "Select current status:",
            ["Responding/Empty", "Patient Onboard"],
            index=0 if "Responding" in user['type'] else 1,
            help="Patient Onboard activates maximum pothole avoidance to protect the patient."
        )
        # Update the active profile based on toggle
        new_profile = f"Ambulance 🚑 ({amb_mode})"
        if new_profile != user['type']:
            st.session_state.user_data['type'] = new_profile
            user = st.session_state.user_data
            st.rerun()

    if st.button("🚪 Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.divider()

    # FIX: capture city_query into session so geocoding stays in sync
    city_input = st.text_input("Digital Twin City", st.session_state.city_query)
    if st.button("Build Graph"):
        with st.spinner("Loading Network..."):
            st.session_state.G           = get_city_graph(city_input)
            st.session_state.city_query  = city_input   # ← store for geocoding
            st.session_state.hazards     = []
            st.session_state.start       = None
            st.session_state.end         = None
            st.rerun()

    st.divider()

    # FIX: allow hazard type selection instead of always "Major Accident"
    from engine import HAZARD_REGISTRY
    hazard_type = st.selectbox("Hazard Type (click map to place)", list(HAZARD_REGISTRY.keys()))
    st.session_state.hazard_type = hazard_type

    st.divider()
    start_addr = st.text_input("Start", "Thrippunithura")
    end_addr   = st.text_input("Destination", "Kakanad")

    if st.button("🚀 Calculate Route"):
        # FIX: use stored city_query instead of hardcoded Kochi string
        context = f", {st.session_state.city_query}"
        try:
            st.session_state.start = ox.geocode(start_addr + context)
            st.session_state.end   = ox.geocode(end_addr   + context)
            st.rerun()
        except Exception as e:
            st.error(f"Address Error: {e}")

# --- MAIN DISPLAY ---
st.title(f"SafeQ Engine | {user['icon']} Mode")

# --- AMBULANCE PATIENT WARNING BANNER ---
if user['type'] == "Ambulance 🚑 (Patient Onboard)":
    st.error(
        "🚨 **PATIENT ONBOARD — Maximum Safety Routing Active** | "
        "Pothole clusters, water logging and all road hazards are being avoided. "
        "Route prioritises smooth roads over speed to protect patient vitals.",
        icon="🚨"
    )
elif user['type'] == "Ambulance 🚑 (Responding/Empty)":
    st.warning(
        "⚡ **RESPONDING MODE — Speed Priority Active** | "
        "Fastest route selected. Switch to 'Patient Onboard' after pickup.",
        icon="⚡"
    )

if st.session_state.G is not None:
    G = st.session_state.G

    m = folium.Map(location=[9.9816, 76.2999], zoom_start=13, tiles=None)
    folium.TileLayer('cartodbdark_matter', name="Dark Mode (Default)").add_to(m)
    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr='Google Satellite',
        name='Satellite View'
    ).add_to(m)
    folium.TileLayer('OpenStreetMap', name="Standard Labels").add_to(m)

    if st.session_state.start and st.session_state.end:
        try:
            orig_n = ox.nearest_nodes(G, st.session_state.start[1], st.session_state.start[0])
            dest_n = ox.nearest_nodes(G, st.session_state.end[1],   st.session_state.end[0])

            # Standard route (red dashed)
            path_std   = nx.shortest_path(G, orig_n, dest_n, weight='length')
            std_coords = [[G.nodes[n]['y'], G.nodes[n]['x']] for n in path_std]
            folium.PolyLine(std_coords, color="#FF4B4B", weight=3,
                            opacity=0.4, dash_array='5').add_to(m)

            # SafeQ route (green)
            path_safe, s_node, e_node = solve_safe_route(
                G, st.session_state.start, st.session_state.end, profile=user['type']
            )
            safe_coords = [[G.nodes[n]['y'], G.nodes[n]['x']] for n in path_safe]
            folium.PolyLine(safe_coords, color="#00ff88", weight=6).add_to(m)

            # Tethering lines
            folium.PolyLine(
                [st.session_state.start, [G.nodes[s_node]['y'], G.nodes[s_node]['x']]],
                color="#00ff88", weight=6
            ).add_to(m)
            folium.PolyLine(
                [st.session_state.end, [G.nodes[e_node]['y'], G.nodes[e_node]['x']]],
                color="#00ff88", weight=6
            ).add_to(m)

            folium.Marker(st.session_state.start, icon=folium.Icon(color='green')).add_to(m)
            folium.Marker(st.session_state.end,   icon=folium.Icon(color='red')).add_to(m)

            # Metrics
            for u, v in zip(path_safe[:-1], path_safe[1:]):
                edge_data  = G.get_edge_data(u, v)[0]
                dist_total += edge_data.get('length', 0)
                risk_score += edge_data.get('risk', 0)

            sensitivity = VEHICLE_PROFILES[user['type']]['sensitivity']
            safety_val  = max(0, 100 - (risk_score * sensitivity * 0.5))

        except Exception as e:
            st.warning(f"Optimization Notice: {e}")

    # Hazard markers
    for h in st.session_state.hazards:
        folium.Marker(h, icon=folium.Icon(color='orange', icon='warning')).add_to(m)

    folium.LayerControl().add_to(m)

    map_data = st_folium(m, width=1100, height=500, key="main_map")

    # FIX: use selected hazard_type instead of hardcoded default
    if map_data and map_data.get('last_clicked'):
        click = (map_data['last_clicked']['lat'], map_data['last_clicked']['lng'])
        if click not in st.session_state.hazards:
            st.session_state.hazards.append(click)
            inject_hazard(
                G, click[0], click[1],
                label=st.session_state.get('hazard_type', 'Pothole Cluster')
            )
            st.rerun()

    # --- ANALYTICS DASHBOARD ---
    st.divider()
    c1, c2, c3 = st.columns([1, 1, 1])

    with c1:
        delta_label = "Hamiltonian Active" if path_safe else "Awaiting Route"
        if user['type'] == "Ambulance 🚑 (Patient Onboard)":
            delta_label = "🚨 Patient Safety Mode"
        elif user['type'] == "Ambulance 🚑 (Responding/Empty)":
            delta_label = "⚡ Speed Priority Mode"
        st.metric("Safety Index", f"{round(safety_val, 1)}%", delta=delta_label)
    with c2:
        st.metric("Path Length", f"{round(dist_total / 1000, 2)} km")
    with c3:
        st.write("")
        show_directions = st.toggle("Show Directions", value=True)

    if path_safe and show_directions:
        st.subheader("📜 Navigation Instructions")
        directions = []
        for u, v in zip(path_safe[:-1], path_safe[1:]):
            edge_data = G.get_edge_data(u, v)[0]
            street    = edge_data.get('name', 'Local Road')
            if not directions or directions[-1] != street:
                directions.append(street)

        directions_html = ""
        for i, step in enumerate(directions):
            street_display  = ", ".join(step) if isinstance(step, list) else step
            directions_html += f"<b>Step {i+1}:</b> Proceed along <i>{street_display}</i><br><br>"

        st.markdown(f"""
            <div style="background-color: #1e2130; padding: 20px; border-radius: 10px;
                        border: 1px solid #333; color: white;">
                {directions_html}
            </div>
            """, unsafe_allow_html=True)

else:
    st.info("👈 Initialize the Digital Twin in the sidebar to start.")