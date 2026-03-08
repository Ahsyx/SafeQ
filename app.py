import streamlit as st
import sys
import os
import json
import folium
import osmnx as ox
from streamlit_folium import st_folium
import networkx as nx

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from engine import get_city_graph, inject_hazard, solve_safe_route, VEHICLE_PROFILES, AMBULANCE_PROFILES
from database import verify_vehicle

DETECTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "detections.json")

def poll_detections(G):
    """
    Reads detections.json, injects any unprocessed hazards into the graph,
    marks them as processed, and returns count of new hazards injected.
    """
    if not os.path.exists(DETECTIONS_FILE):
        return 0
    try:
        with open(DETECTIONS_FILE) as f:
            records = json.load(f)
    except Exception:
        return 0

    injected = 0
    for record in records:
        if record.get("processed"):
            continue
        lat = record["lat"]
        lon = record["lon"]
        for det in record.get("detections", []):
            success = inject_hazard(G, lat, lon, label=det["hazard"])
            if success:
                if (lat, lon) not in st.session_state.hazards:
                    st.session_state.hazards.append((lat, lon))
                injected += 1
        record["processed"] = True  # mark done

    if injected:
        with open(DETECTIONS_FILE, "w") as f:
            json.dump(records, f, indent=2)

    return injected

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
    'original_path': None,   # stores naive shortest path before any hazard
    'city_query': "Kochi, Kerala, India"
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Maps old database vehicle type names → new profile names
# Needed because database.py still returns the old string keys
VEHICLE_TYPE_MAP = {
    "Ambulance (Emergency)": "Ambulance 🚑 (Responding/Empty)",
    "Standard Car":          "Standard Car",
    "School Bus":            "School Bus",
    "Two-Wheeler":           "Two-Wheeler",
    "Heavy Truck":           "Heavy Truck",
}

def resolve_vehicle_type(v_type):
    """Safely maps any vehicle type string to a known VEHICLE_PROFILES key."""
    return VEHICLE_TYPE_MAP.get(v_type, v_type)

# ==========================================
from auth import signup, login as auth_login

# ==========================================
# 🔐 LOGIN / SIGNUP GATE
# ==========================================
if not st.session_state.logged_in:
    st.title("🛡️ SafeQ: Autonomous Safety Dashboard")
    st.caption("Smart road hazard detection & safe routing system")
    st.divider()

    tab_login, tab_signup = st.tabs(["🔑 Login", "📝 Sign Up"])

    # ── LOGIN ────────────────────────────────────────────────────────────
    with tab_login:
        st.subheader("Welcome back")
        username  = st.text_input("Username", key="login_user")
        password  = st.text_input("Password", type="password", key="login_pass")

        if st.button("Sign In", key="btn_login"):
            if username and password:
                ok, result = auth_login(username, password)
                if ok:
                    v_type = resolve_vehicle_type(result["vehicle_type"])
                    st.session_state.user_data = {
                        "reg_id": result["reg_number"],
                        "type":   v_type,
                        "icon":   VEHICLE_PROFILES[v_type]['icon'],
                        "name":   result.get("name", username)
                    }
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error(f"❌ {result}")
            else:
                st.warning("Please enter username and password.")

        st.divider()
        st.caption("Demo accounts — Registration Number: `KL-07-AW-1234` (Ambulance), `KL-40-Q-9999` (Two-Wheeler)")

    # ── SIGNUP ───────────────────────────────────────────────────────────
    with tab_signup:
        st.subheader("Create your account")

        new_username = st.text_input("Username",           key="su_user", placeholder="e.g. ashik")
        new_password = st.text_input("Password",           key="su_pass", type="password", placeholder="Min 6 characters")
        new_reg      = st.text_input("Vehicle Reg Number", key="su_reg",  placeholder="e.g. KL-07-AW-1234")

        # Auto-detect vehicle type from VAHAN database as user types
        detected_vtype = None
        if new_reg:
            detected_vtype = resolve_vehicle_type(verify_vehicle(new_reg))
            if detected_vtype and detected_vtype != "Standard Car":
                st.success(f"✅ VAHAN Database: **{detected_vtype}** detected for `{new_reg.upper()}`")
            else:
                st.info(f"🚗 VAHAN Database: Registered as **Standard Car** (or unrecognised plate)")

        if st.button("Create Account", key="btn_signup"):
            if new_username and new_password and new_reg:
                final_vtype = detected_vtype or "Standard Car"
                ok, msg = signup(new_username, new_password, new_reg, final_vtype)
                if ok:
                    st.success(f"✅ {msg} Registered as **{final_vtype}**. Please log in.")
                else:
                    st.error(f"❌ {msg}")
            else:
                st.warning("Please fill all fields.")

        st.divider()
        st.caption("🔍 Try: `KL-07-AW-1234` (Ambulance) · `KL-40-Q-9999` (Two-Wheeler) · `KL-01-BT-5555` (School Bus)")

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
    st.success(f"👤 {user.get('name', user['reg_id'])}")
    st.info(f"🚗 {user['reg_id']} | {user['icon']} {user['type']}")

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

    # Reset hazards button
    if st.session_state.get('hazards'):
        st.divider()
        if st.button("🔄 Clear All Hazards & Recalculate"):
            # Clear hazards from session
            st.session_state.hazards = []
            # Reset all edge risks in graph
            G_reset = st.session_state.get('G')
            if G_reset:
                for u, v, k, d in G_reset.edges(keys=True, data=True):
                    d['risk'] = 0.0
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
        context = f", {st.session_state.city_query}"
        try:
            st.session_state.start         = ox.geocode(start_addr + context)
            st.session_state.end           = ox.geocode(end_addr   + context)
            st.session_state.original_path = None  # reset so red line recaptures clean path
            st.rerun()
        except Exception as e:
            st.error(f"Address Error: {e}")

    if st.session_state.get('start') or st.session_state.get('end'):
        if st.button("🔄 Reset Route"):
            st.session_state.start = None
            st.session_state.end   = None
            st.rerun()

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

    # ── Auto-refresh every 5 seconds to pick up new detections ───────────
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=5000, key="detector_poll")

    # ── Poll detector.py output file for new hazards ──────────────────────
    new_hazards = poll_detections(G)
    if new_hazards:
        st.toast(f"📡 {new_hazards} new hazard(s) detected by scanner — map updated!", icon="⚠️")

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
            # Standard route (red dashed) — frozen on first calc, never changes after hazards
            orig_n = ox.nearest_nodes(G, st.session_state.start[1], st.session_state.start[0])
            dest_n = ox.nearest_nodes(G, st.session_state.end[1],   st.session_state.end[0])

            if not st.session_state.original_path:
                st.session_state.original_path = nx.shortest_path(G, orig_n, dest_n, weight='length')
            path_std   = st.session_state.original_path
            std_coords = [[G.nodes[n]['y'], G.nodes[n]['x']] for n in path_std]

            # SafeQ route (green) — recalculates with hazard weights every time
            path_safe, s_node, e_node = solve_safe_route(
                G, st.session_state.start, st.session_state.end, profile=user['type']
            )
            safe_coords = [[G.nodes[n]['y'], G.nodes[n]['x']] for n in path_safe]

            routes_differ = path_safe != path_std

            # Red = original naive route (always shown for comparison)
            folium.PolyLine(std_coords, color="#FF4B4B",
                            weight=5 if routes_differ else 3,
                            opacity=0.85 if routes_differ else 0.4,
                            dash_array='10',
                            tooltip="⚠️ Original Shortest Route (ignores hazards)").add_to(m)

            # Green = SafeQ safe route
            folium.PolyLine(safe_coords, color="#00ff88", weight=7,
                            tooltip="✅ SafeQ Safe Route").add_to(m)

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
            route_max_risk = 0
            for u, v in zip(path_safe[:-1], path_safe[1:]):
                edge_data   = G.get_edge_data(u, v)[0]
                dist_total += edge_data.get('length', 0)
                risk_score += edge_data.get('risk', 0)
                route_max_risk = max(route_max_risk, edge_data.get('risk', 0))

            # FIX: safety index — 100% when no risk, drops proportionally
            # risk_score is raw sum of hazard severities on path
            # normalize against max possible (95 = Major Accident severity)
            total_edges  = max(len(path_safe) - 1, 1)
            avg_risk     = risk_score / total_edges
            sensitivity  = VEHICLE_PROFILES[user['type']]['sensitivity']
            safety_val   = max(0.0, 100.0 - min(avg_risk * sensitivity, 100.0))

            # Route status banners
            if routes_differ:
                st.success("✅ **SafeQ rerouted** — green line avoids the hazard. Red = original shortest path.")
            elif route_max_risk > 0:
                st.warning(
                    f"⚠️ **No bypass available** — safest path still passes hazard zone "
                    f"(risk={route_max_risk:.0f}). Road network has no alternative here."
                )

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

# ── Detection Log pulled from detector page ──────────────────────────────────
if st.session_state.get('detection_log'):
    st.divider()
    st.subheader("📋 Live Detection Feed")
    st.caption("Hazards reported by the Detector page appear here in real-time")
    log = st.session_state.detection_log[::-1][:5]  # latest 5
    for entry in log:
        st.markdown(f"""
            <div style="background-color:#1e2130; padding:12px; border-radius:8px;
                        border-left:4px solid #ff4b4b; margin-bottom:8px; color:white;">
                🕐 <b>{entry['time']}</b> &nbsp;|&nbsp;
                ⚠️ {entry['hazard']} &nbsp;|&nbsp;
                🎯 {entry['conf']:.0%} &nbsp;|&nbsp;
                📍 ({entry['lat']:.4f}, {entry['lon']:.4f}) &nbsp;|&nbsp;
                🚗 {entry['reporter']}
            </div>
        """, unsafe_allow_html=True)