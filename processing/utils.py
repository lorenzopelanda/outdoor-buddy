import osmnx as ox
import networkx as nx
import gpxpy.gpx
from geopy.geocoders import Nominatim
import random


def get_coordinates(address):
    """Restituisce le coordinate (lat, lon) date un indirizzo."""
    geolocator = Nominatim(user_agent="route_planner_bot")
    location = geolocator.geocode(address)
    if location:
        return location.latitude, location.longitude
    else:
        raise ValueError("Indirizzo non trovato.")


def get_training_params(level):
    """Imposta i parametri in base al livello di allenamento."""
    levels = {
        "principiante": {"max_distance": 10_000, "max_elevation_gain": 200},
        "intermedio": {"max_distance": 30_000, "max_elevation_gain": 500},
        "avanzato": {"max_distance": 70_000, "max_elevation_gain": 1000},
    }
    return levels.get(level, levels["intermedio"])


def plan_circular_route(address, desired_distance_km, training_level, mode="bike", output_file="suggested_route.gpx"):
    """
    Suggerisce un percorso circolare basato su livello di allenamento, distanza desiderata e indirizzo di partenza.

    Args:
        address (str): Indirizzo di partenza.
        desired_distance_km (float): Distanza desiderata in km.
        training_level (str): Livello di allenamento: "principiante", "intermedio", "avanzato".
        mode (str): Modalità di viaggio: "bike" o "walk".
        output_file (str): Nome del file GPX in uscita.
    """
    # Ottieni le coordinate dell’indirizzo
    start_lat, start_lon = get_coordinates(address)

    # Imposta i parametri di allenamento
    params = get_training_params(training_level)
    max_distance_m = desired_distance_km * 1000

    # Scarica la rete stradale
    G = ox.graph_from_point((start_lat, start_lon), dist=max_distance_m * 1.5, network_type=mode)

    # Trova il nodo più vicino al punto di partenza
    start_node = ox.distance.nearest_nodes(G, start_lon, start_lat)

    # Cerca un nodo di ritorno casuale per rendere il percorso circolare
    nodes = list(G.nodes())
    random_node = random.choice(nodes)

    # Calcola il percorso di andata
    route_to_random = nx.shortest_path(G, start_node, random_node, weight="length")

    # Calcola il percorso di ritorno
    route_back = nx.shortest_path(G, random_node, start_node, weight="length")

    # Unisci i percorsi per ottenere un circuito
    route = route_to_random + route_back[1:]

    # Calcola la lunghezza totale
    route_length = sum(nx.get_edge_attributes(G, "length")[edge] for edge in zip(route[:-1], route[1:]))

    # Verifica che la distanza sia simile a quella desiderata
    if abs(route_length - max_distance_m) > 0.3 * max_distance_m:
        print("Nessun percorso circolare trovato con la distanza desiderata.")
        return

    # Salva il percorso in GPX
    gdf_nodes, _ = ox.graph_to_gdfs(G, nodes=True, edges=True)
    gdf_route = gdf_nodes.loc[route]

    gpx = gpxpy.gpx.GPX()
    track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(track)
    segment = gpxpy.gpx.GPXTrackSegment()

    for _, node in gdf_route.iterrows():
        segment.points.append(gpxpy.gpx.GPXTrackPoint(node["y"], node["x"]))
    track.segments.append(segment)

    with open(output_file, "w") as f:
        f.write(gpx.to_xml())

    print(f"Percorso circolare suggerito: {route_length / 1000:.2f} km, salvato in {output_file}")
