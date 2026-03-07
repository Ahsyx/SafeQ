import streamlit as st
import sys
import os
import folium
import osmnx as ox
from streamlit_folium import st_folium
import networkx as nx
import pandas as pd

# Force local module recognition
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from engine import get_city_graph, inject_hazard, solve_safe_route

# --- PAGE CONFIG ---
st.set_page_config(page_title="SafeQ Global", layout="wide", page_icon="🛡️")

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #00ff88; color: black; font-weight: bold; }
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #333; }
    </style>
    """, unsafe_allow_html=True)

# --- SESSION STATE ---
if 'G' not in st.session_state:
    st.session_state.G = None
    st.session_state.start, st.session_state.end, st.session_state.hazards = None, None, []

# --- SIDEBAR ---
with st.sidebar:
    st.title("🛡️ SafeQ Control")
    city_query = st.text_input("1. Search City", "Kochi, Kerala, India")
    
    if st.button("🗺️ Build Digital Twin"):
        with st.spinner(f"Mapping {city_query}..."):
            graph = get_city_graph(city_query)
            if graph:
                st.session_state.G = graph
                st.session_state.start, st.session_state.end, st.session_state.hazards = None, None, []
                st.success("Network Live!")
                st.rerun()

    st.divider()
    st.subheader("2. Navigation Search")
    start_addr = st.text_input("Start Location", "Thrippunithura, Kochi")
    end_addr = st.text_input("Destination", "Kakanad, Kochi")
    
    if st.button("🚀 Calculate SafeQ Path"):
        try:
            st.session_state.start = ox.geocode(start_addr)
            st.session_state.end = ox.geocode(end_addr)
            st.rerun()
        except:
            st.error("Address not found.")

    st.divider()
    if st.button("♻️ Reset Everything"):
        st.session_state.start, st.session_state.end, st.session_state.hazards = None, None, []
        st.rerun()

# --- MAIN DISPLAY ---
st.title("SafeQ: Autonomous Safety Navigation")

if st.session_state.G is not None:
    G = st.session_state.G
    gdf_nodes = ox.graph_to_gdfs(G, edges=False)
    map_center = st.session_state.start if st.session_state.start else [gdf_nodes.y.mean(), gdf_nodes.x.mean()]
    m = folium.Map(location=map_center, zoom_start=14, tiles=None)

    # --- ADD DIFFERENT VIEWS ---
    folium.TileLayer('cartodbdark_matter', name='Dark Mode (SafeQ Default)').add_to(m)
    folium.TileLayer('openstreetmap', name='Street Map (Standard)').add_to(m)
    folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satellite View').add_to(m)

    # Variables for Analytics
    risk_std, risk_safe = 0, 0
    dist_std, dist_safe = 0, 0

    if st.session_state.start and st.session_state.end:
        try:
            orig = ox.nearest_nodes(G, st.session_state.start[1], st.session_state.start[0])
            dest = ox.nearest_nodes(G, st.session_state.end[1], st.session_state.end[0])
            
            # A. Standard Route
            path_std = nx.shortest_path(G, orig, dest, weight='length')
            folium.PolyLine([[G.nodes[n]['y'], G.nodes[n]['x']] for n in path_std], color="red", weight=2, dash_array='5', opacity=0.4).add_to(m)
            
            # B. SafeQ Route
            path_safe = solve_safe_route(G, st.session_state.start, st.session_state.end)
            folium.PolyLine([[G.nodes[n]['y'], G.nodes[n]['x']] for n in path_safe], color="#00ff88", weight=6, opacity=0.9).add_to(m)
            
            # C. Calculate Metrics
            for u, v in zip(path_std[:-1], path_std[1:]):
                edge_data = G.get_edge_data(u, v)[0]
                risk_std += edge_data.get('risk', 0)
                dist_std += edge_data.get('length', 0)
            
            for u, v in zip(path_safe[:-1], path_safe[1:]):
                edge_data = G.get_edge_data(u, v)[0]
                risk_safe += edge_data.get('risk', 0)
                dist_safe += edge_data.get('length', 0)

            # Markers
            folium.Marker([G.nodes[orig]['y'], G.nodes[orig]['x']], icon=folium.Icon(color='green', icon='play')).add_to(m)
            folium.Marker([G.nodes[dest]['y'], G.nodes[dest]['x']], icon=folium.Icon(color='red', icon='stop')).add_to(m)

        except Exception as e:
            st.warning(f"Routing Update: {e}")

    for h in st.session_state.hazards:
        folium.Marker(h, icon=folium.Icon(color='orange', icon='warning')).add_to(m)

    folium.LayerControl().add_to(m)
    map_data = st_folium(m, width=1100, height=500, key="main_map")

    # --- SAFETY DASHBOARD PANEL ---
    st.divider()
    st.subheader("📊 Real-Time Safety Analytics")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.metric("Hazards Detected", len(st.session_state.hazards), delta="YOLOv8 Active")
    with c2:
        risk_reduction = risk_std - risk_safe
        st.metric("Risk Avoided", f"{risk_reduction} Units", delta="SafeQ Logic", delta_color="normal")
    with c3:
        extra_dist = max(0, dist_safe - dist_std)
        st.metric("Efficiency Trade-off", f"+{round(extra_dist)}m", delta="Worth for Safety", delta_color="inverse")

    if map_data['last_clicked']:
        click = (map_data['last_clicked']['lat'], map_data['last_clicked']['lng'])
        if st.session_state.start is None: st.session_state.start = click; st.rerun()
        elif st.session_state.end is None: st.session_state.end = click; st.rerun()
        else:
            if click not in st.session_state.hazards:
                st.session_state.hazards.append(click)
                inject_hazard(G, click[0], click[1])
                st.rerun()
else:
    st.info("👈 Build the Digital Twin in the sidebar to start.")