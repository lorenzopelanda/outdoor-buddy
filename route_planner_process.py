#!/usr/bin/env python3
import json
import sys
import logging
import os
import traceback

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
        from processing.utils import plan_circular_route

        # Run the route planning function
        plan_circular_route(
            params["address"],
            params["distance"],
            params["level"],
            output_file=params["output_file"]
        )

        # If we get here, it was successful
        return 0
    except Exception as e:
        logger.error(f"Route planning failed: {e}")
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())