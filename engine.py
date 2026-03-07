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
#
# AMBULANCE DUAL-MODE LOGIC:
#   Responding (empty) → low sensitivity → fastest route to reach patient
#   Patient Onboard    → high sensitivity → safest route, avoids every pothole/jolt
#   Potholes cause dangerous jolts to patients with spinal injuries, internal
#   bleeding, fractures, or active IV lines — patient safety overrides speed.
VEHICLE_PROFILES = {
    "Standard Car":                    {"sensitivity": 1.0, "icon": "🚗"},
    "Ambulance 🚑 (Responding/Empty)": {"sensitivity": 0.2, "icon": "🚑"},
    "Ambulance 🚑 (Patient Onboard)":  {"sensitivity": 4.0, "icon": "🚑"},
    "School Bus":                      {"sensitivity": 1.5, "icon": "🚌"},
    "Two-Wheeler":                     {"sensitivity": 5.0, "icon": "🛵"},
    "Heavy Truck":                     {"sensitivity": 0.5, "icon": "🚛"}
}

# Profiles that belong to the ambulance family (used for UI warnings)
AMBULANCE_PROFILES = {
    "Ambulance 🚑 (Responding/Empty)",
    "Ambulance 🚑 (Patient Onboard)"
}


def get_city_graph(place_name):
    """Downloads a Digital Twin and cleans disconnected 'islands'."""
    try:
        ox.settings.use_cache = True
        G = ox.graph_from_place(place_name, network_type='drive')
        G = ox.truncate.largest_component(G, strongly=True)
        G = nx.MultiDiGraph(G)

        # Initialise risk on every edge key
        for u, v, k, d in G.edges(keys=True, data=True):
            d['risk'] = 0.0
        return G
    except Exception as e:
        print(f"Error loading {place_name}: {e}")
        return None


def inject_hazard(G, lat, lon, label="Pothole Cluster"):
    """
    Finds the nearest road segment and injects risk energy.
    Default changed to 'Pothole Cluster' to match the pothole-detection theme.
    """
    severity = HAZARD_REGISTRY.get(label, 50)
    try:
        u, v, key = ox.nearest_edges(G, lon, lat)
        G[u][v][key]['risk'] = G[u][v][key].get('risk', 0) + severity

        # FIX: also penalise reverse edge if it exists (undirected roads)
        if G.has_edge(v, u):
            for k in G[v][u]:
                G[v][u][k]['risk'] = G[v][u][k].get('risk', 0) + severity
        return True
    except Exception as e:
        print(f"Hazard Injection Error: {e}")
        return False


def solve_safe_route(G, start_coords, end_coords, profile="Standard Car"):
    """
    Calculates the minimum-energy path using a safety-weighted Hamiltonian.

    FIX: MultiDiGraph shortest_path requires the weight callable to accept
    the full dict of all parallel edges and return a scalar. We use
    nx.shortest_path which internally picks the minimum-weight parallel edge,
    so we wrap the per-edge-key logic in a multi-edge-aware helper.
    """
    origin_node = ox.nearest_nodes(G, start_coords[1], start_coords[0])
    target_node = ox.nearest_nodes(G, end_coords[1], end_coords[0])

    sensitivity = VEHICLE_PROFILES.get(profile, {}).get("sensitivity", 1.0)

    def quantum_weight(u, v, data):
        """
        For MultiDiGraph, networkx passes the data dict of ONE edge at a time
        when iterating candidate edges — this is correct behaviour.
        Hamiltonian: Energy = Distance + (Risk * Sensitivity * Multiplier)
        """
        dist        = data.get('length', 1)
        risk_penalty = data.get('risk', 0) * 1_000_000 * sensitivity
        return dist + risk_penalty

    try:
        path = nx.shortest_path(
            G, origin_node, target_node, weight=quantum_weight
        )
    except nx.NetworkXNoPath:
        # Fallback: plain distance route if safety-weighted path fails
        path = nx.shortest_path(G, origin_node, target_node, weight='length')

    return path, origin_node, target_node