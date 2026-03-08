import osmnx as ox
import networkx as nx

# 1. The Hazard "Brain"
HAZARD_REGISTRY = {
    "Major Accident": 95,
    "Pothole Cluster": 45,
    "Water Logging": 70,
    "Construction": 30
}

# 2. The Vehicle Profile Registry
VEHICLE_PROFILES = {
    "Standard Car":                    {"sensitivity": 1.0, "icon": "🚗"},
    "Ambulance 🚑 (Responding/Empty)": {"sensitivity": 0.2, "icon": "🚑"},
    "Ambulance 🚑 (Patient Onboard)":  {"sensitivity": 4.0, "icon": "🚑"},
    "School Bus":                      {"sensitivity": 1.5, "icon": "🚌"},
    "Two-Wheeler":                     {"sensitivity": 5.0, "icon": "🛵"},
    "Heavy Truck":                     {"sensitivity": 0.5, "icon": "🚛"}
}

AMBULANCE_PROFILES = {"Ambulance 🚑 (Responding/Empty)", "Ambulance 🚑 (Patient Onboard)"}

# --- 🔥 FINAL EMERGENCY CALIBRATION ---
# 500 is the 'Safe Standard'. It forces a detour only if a 
# REAL road alternative is nearby.
RISK_MULTIPLIER = 500 

def get_city_graph(place_name):
    """Downloads a Digital Twin and STRICTLY filters for major car roads only."""
    try:
        ox.settings.use_cache = True
        
        # FIX: ONLY download major and residential roads. 
        # This deletes the 'house paths' from the database entirely.
        cf = '["highway"~"motorway|trunk|primary|secondary|tertiary|residential"]'
        
        G = ox.graph_from_place(place_name, network_type='drive', custom_filter=cf)
        G = ox.truncate.largest_component(G, strongly=True)
        G = nx.MultiDiGraph(G)

        for u, v, k, d in G.edges(keys=True, data=True):
            d['risk'] = 0.0
        return G
    except Exception as e:
        print(f"Error loading {place_name}: {e}")
        return None

def inject_hazard(G, lat, lon, label="Pothole Cluster"):
    """Blocks all parallel lanes at the hazard location."""
    severity = HAZARD_REGISTRY.get(label, 50)
    try:
        u, v, key = ox.nearest_edges(G, lon, lat)
        for nodes in [(u, v), (v, u)]:
            if G.has_edge(*nodes):
                for k in G[nodes[0]][nodes[1]]:
                    G[nodes[0]][nodes[1]][k]['risk'] = G[nodes[0]][nodes[1]][k].get('risk', 0) + severity
        return True
    except: return False

def solve_safe_route(G, start_coords, end_coords, profile="Standard Car"):
    """Calculates the minimum-energy path using safety-weighted Hamiltonian."""
    origin_node = ox.nearest_nodes(G, start_coords[1], start_coords[0])
    target_node = ox.nearest_nodes(G, end_coords[1], end_coords[0])
    sensitivity = VEHICLE_PROFILES.get(profile, {}).get("sensitivity", 1.0)

    # --- 🔥 THE PHYSICS WEIGHT FUNCTION ---
    def quantum_weight(u, v, data):
        dist = data.get('length', 1)
        
        # 1. RISK BARRIER
        # At 500 multiplier, a hazard adds a 'virtual' 47km for Patient Onboard (4.0 sensitivity)
        # This forces a detour but keeps the ball on the road 'track'.
        risk_penalty = data.get('risk', 0) * RISK_MULTIPLIER * sensitivity
        
        return dist + risk_penalty

    try:
        path = nx.shortest_path(G, origin_node, target_node, weight=quantum_weight)
    except nx.NetworkXNoPath:
        path = nx.shortest_path(G, origin_node, target_node, weight='length')

    return path, origin_node, target_node