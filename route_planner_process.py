#!/usr/bin/env python3
import json
import sys
import logging
import os
import traceback
import sklearn
import gc  # Garbage collection

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("route_planner")

# Make sure we can import from the project
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def main():
    try:
        # Read the JSON parameters file passed as argument
        if len(sys.argv) < 2:
            logger.error("No parameters file provided")
            return 1

        with open(sys.argv[1], 'r') as f:
            params = json.load(f)

        # Import here to ensure path is set up correctly
        from processing.utils import get_coordinates, get_training_params

        # We'll implement our own memory-optimized version of plan_circular_route
        address = params["address"]
        desired_distance_km = params["distance"]
        training_level = params["level"]
        output_file = params["output_file"]
        mode = "bike"

        # Get coordinates and parameters first
        start_lat, start_lon = get_coordinates(address)
        logger.info(f"Coordinates for address {address}: {start_lat}, {start_lon}")

        # Get training parameters
        training_params = get_training_params(training_level)
        logger.info(f"Training params: {training_params}")

        # Calculate max distance in meters
        max_distance_m = desired_distance_km * 1000
        logger.info(f"Max distance in meters: {max_distance_m}")

        # Import OSMnx and NetworkX here to control memory
        import osmnx as ox
        import networkx as nx
        import gpxpy.gpx
        import random

        # Configure OSMnx to use less memory
        ox.settings.use_cache=True
        ox.settings.log_console=True
        ox.settings.log_file = True

        # Download the graph with a smaller search radius first
        logger.info("Downloading initial graph with smaller radius...")
        initial_radius = min(5000, max_distance_m * 0.3)  # Start with smaller radius
        G = ox.graph_from_point((start_lat, start_lon), dist=initial_radius, network_type=mode, simplify=True)

        # Incrementally expand if needed
        max_iterations = 5
        current_iteration = 0
        route_found = False

        while not route_found and current_iteration < max_iterations:
            try:
                # Find the nearest node to the starting point
                start_node = ox.distance.nearest_nodes(G, start_lon, start_lat)

                # Get a sample of nodes to try as destinations
                nodes = list(G.nodes())
                sample_size = min(20, len(nodes))
                sample_nodes = random.sample(nodes, sample_size)

                # Try to find a route to any of these nodes and back
                for target_node in sample_nodes:
                    if target_node == start_node:
                        continue

                    try:

                        # Find route to target
                        route_to = nx.shortest_path(G, start_node, target_node, weight="length")

                        # Find route back
                        route_back = nx.shortest_path(G, target_node, start_node, weight="length")

                        # Combine routes
                        route = route_to + route_back[1:]

                        # Calculate total length
                        route_length = sum(ox.utils_graph.get_route_edge_attributes(G, route, "length"))

                        # Check if route length is close enough to desired distance
                        if 0.7 * max_distance_m <= route_length <= 1.3 * max_distance_m:
                            logger.info(f"Found suitable route with length: {route_length / 1000:.2f} km")
                            route_found = True
                            break
                    except nx.NetworkXNoPath:
                        continue

                # If we couldn't find a good route, expand the graph
                if not route_found:
                    current_iteration += 1
                    if current_iteration >= max_iterations:
                        break

                    # Expand search radius
                    new_radius = initial_radius * (1 + current_iteration)
                    new_radius = min(new_radius, max_distance_m * 0.8)  # Cap maximum radius

                    logger.info(
                        f"Expanding graph with radius: {new_radius / 1000:.2f} km (iteration {current_iteration})")

                    # Clean up memory before downloading more
                    del G
                    gc.collect()

                    # Download larger graph
                    G = ox.graph_from_point((start_lat, start_lon), dist=new_radius, network_type=mode, simplify=True)

            except Exception as e:
                logger.error(f"Error during route finding: {e}")
                current_iteration += 1

                # Try again with a smaller graph
                del G
                gc.collect()

                new_radius = initial_radius * (0.8 ** current_iteration)
                logger.info(f"Retrying with smaller radius: {new_radius / 1000:.2f} km")
                G = ox.graph_from_point((start_lat, start_lon), dist=new_radius, network_type=mode, simplify=True)

        if not route_found:
            logger.error("Failed to find a suitable route after multiple attempts")
            return 1

        # Create GPX file from route
        logger.info("Creating GPX file...")
        gdf_nodes = ox.graph_to_gdfs(G, nodes=route, edges=False)

        gpx = gpxpy.gpx.GPX()
        track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(track)
        segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(segment)

        for _, row in gdf_nodes.iterrows():
            segment.points.append(gpxpy.gpx.GPXTrackPoint(row["y"], row["x"]))

        with open(output_file, "w") as f:
            f.write(gpx.to_xml())

        logger.info(f"Route saved to {output_file}")
        return 0
    except Exception as e:
        logger.error(f"Route planning failed: {e}")
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())