import osmnx as ox
import networkx as nx

# 1. The Hazard "Brain"
HAZARD_REGISTRY = {
    "Major Accident": 95,
    "Pothole Cluster": 45,
    "Water Logging": 70,
    "Construction": 30
}

def get_city_graph(place_name):
    """Downloads a Digital Twin and cleans disconnected 'islands'."""
    try:
        ox.settings.use_cache = True
        G = ox.graph_from_place(place_name, network_type='drive')
        
        # API FIX: Keep only the largest strongly connected component
        G = ox.truncate.largest_component(G, strongly=True)
        
        G = nx.MultiDiGraph(G)
        
        # Initialize all edges with 0 risk upfront
        for u, v, k, d in G.edges(keys=True, data=True):
            d['risk'] = 0.0
            
        return G
    except Exception as e:
        print(f"Error loading {place_name}: {e}")
        return None

def inject_hazard(G, lat, lon, label="Major Accident"):
    """Finds the nearest road segment and injects 'High Energy' risk."""
    severity = HAZARD_REGISTRY.get(label, 50)
    try:
        u, v, key = ox.nearest_edges(G, lon, lat)
        G[u][v][key]['risk'] += severity
        return True
    except Exception as e:
        print(f"Hazard Injection Error: {e}")
        return False

def solve_safe_route(G, start_coords, end_coords):
    """Calculates the global minimum energy path via safety-weighted Hamiltonian."""
    origin_node = ox.nearest_nodes(G, start_coords[1], start_coords[0])
    target_node = ox.nearest_nodes(G, end_coords[1], end_coords[0])

    def quantum_weight(u, v, d):
        # Hamiltonian: Energy = Distance + (Risk * 1,000,000 Penalty)
        return d.get('length', 1) + (d.get('risk', 0) * 1000000.0)

    return nx.shortest_path(G, origin_node, target_node, weight=quantum_weight)