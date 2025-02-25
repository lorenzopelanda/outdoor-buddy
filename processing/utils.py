import osmnx as ox
import networkx as nx
import gpxpy.gpx
from geopy.geocoders import Nominatim
import random
import logging
import sys


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_coordinates(address):
    geolocator = Nominatim(user_agent="route_planner_bot")
    location = geolocator.geocode(address)
    if location:
        return location.latitude, location.longitude
    else:
        raise ValueError("Address not found.")


def get_training_params(level):
    levels = {
        "beginner": {"max_distance": 20_000, "max_elevation_gain": 300},
        "intermediate": {"max_distance": 70_000, "max_elevation_gain": 800},
        "advanced": {"max_distance": 120_000, "max_elevation_gain": 1500},
    }
    return levels.get(level, levels["intermediate"])


def plan_circular_route(address, desired_distance_km, training_level, mode="bike", output_file="bike_route.gpx"):
    try:
        logger.info(f"Planning route for address: {address}, distance: {desired_distance_km}, level: {training_level}")
        start_lat, start_lon = get_coordinates(address)
        logger.info(f"Coordinates for address {address}: {start_lat}, {start_lon}")

        params = get_training_params(training_level)
        logger.info(f"Training params: {params}")

        max_distance_m = desired_distance_km * 1000
        logger.info(f"Max distance in meters: {max_distance_m}")

        G = ox.graph_from_point((start_lat, start_lon), dist=max_distance_m * 1.5, network_type=mode)

        start_node = ox.distance.nearest_nodes(G, start_lon, start_lat)

        nodes = list(G.nodes())
        random_node = random.choice(nodes)

        route_to_random = nx.shortest_path(G, start_node, random_node, weight="length")

        route_back = nx.shortest_path(G, random_node, start_node, weight="length")

        route = route_to_random + route_back[1:]

        route_length = sum(nx.get_edge_attributes(G, "length")[edge] for edge in zip(route[:-1], route[1:]))

        if abs(route_length - max_distance_m) > 0.3 * max_distance_m:
            print("No route found for the address and distance.")
            return

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

        print(f"Suggested circular route: {route_length / 1000:.2f} km, saved in {output_file}")
    except Exception as e:
        logger.error(f"Error during route planning: {e}")
        raise
