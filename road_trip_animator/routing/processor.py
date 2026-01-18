"""
Route processor for calculating routes between waypoints using OpenStreetMap routing.

This module provides the RouteProcessor class that handles route calculation,
waypoint validation, and chronological ordering of trip data.
"""

import math
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any
import requests
from ..models import Waypoint, RouteSegment, Route, Coordinates
from ..validation import ValidationError, validate_coordinate_range
from .custom_routes import CustomRouteManager


class RouteProcessor:
    """
    Calculate routes between waypoints using road networks.
    
    This class handles route calculation using OpenStreetMap routing services,
    validates waypoints, and ensures chronological ordering of trip data.
    """
    
    def __init__(self, user_agent: str = "road_trip_map_animator", rate_limit_delay: float = 1.0):
        """
        Initialize the route processor.
        
        Args:
            user_agent: User agent string for API requests
            rate_limit_delay: Delay between API requests in seconds
        """
        self.user_agent = user_agent
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0.0
        
        # OpenStreetMap routing service (OSRM demo server)
        self.routing_base_url = "http://router.project-osrm.org/route/v1/driving"
        
        # Custom route manager
        self.custom_route_manager = CustomRouteManager()
    
    def calculate_route_segments(self, waypoints: List[Waypoint]) -> List[RouteSegment]:
        """
        Calculate route segments between consecutive waypoints.
        
        Args:
            waypoints: List of waypoints (must be chronologically ordered)
            
        Returns:
            List of route segments connecting the waypoints
            
        Raises:
            ValidationError: If waypoints are invalid or routing fails
        """
        if not waypoints:
            raise ValidationError("Cannot calculate route segments for empty waypoint list")
        
        if len(waypoints) < 2:
            return []  # Single waypoint has no segments
        
        # Validate waypoints are chronologically ordered
        self._validate_chronological_order(waypoints)
        
        # Validate all waypoints are within reasonable bounds
        self._validate_waypoint_bounds(waypoints)
        
        segments = []
        for i in range(len(waypoints) - 1):
            start_waypoint = waypoints[i]
            end_waypoint = waypoints[i + 1]
            
            try:
                segment = self._calculate_single_segment(start_waypoint, end_waypoint)
                segments.append(segment)
            except Exception as e:
                # If routing fails, create a fallback segment with straight-line path
                fallback_segment = self._create_fallback_segment(start_waypoint, end_waypoint)
                segments.append(fallback_segment)
                print(f"Warning: Routing failed for segment {i}, using fallback: {e}")
        
        return segments
    
    def sort_waypoints_chronologically(self, waypoints: List[Waypoint]) -> Tuple[List[Waypoint], bool]:
        """
        Sort waypoints chronologically by timestamp.
        
        Args:
            waypoints: List of waypoints to sort
            
        Returns:
            Tuple of (sorted_waypoints, was_reordered)
        """
        if not waypoints:
            return waypoints, False
        
        # Check if already sorted
        is_sorted = all(
            waypoints[i].timestamp <= waypoints[i + 1].timestamp
            for i in range(len(waypoints) - 1)
        )
        
        if is_sorted:
            return waypoints, False
        
        # Sort by timestamp
        sorted_waypoints = sorted(waypoints, key=lambda wp: wp.timestamp)
        return sorted_waypoints, True
    
    def validate_waypoints_bounds(self, waypoints: List[Waypoint]) -> List[str]:
        """
        Validate that waypoints fall within reasonable geographic bounds.
        
        Args:
            waypoints: List of waypoints to validate
            
        Returns:
            List of validation error messages (empty if all valid)
        """
        errors = []
        
        for i, waypoint in enumerate(waypoints):
            try:
                validate_coordinate_range(waypoint.latitude, waypoint.longitude)
            except ValidationError as e:
                errors.append(f"Waypoint {i} ({waypoint.location_name}): {e}")
        
        return errors
    
    def create_route_from_waypoints(self, waypoints: List[Waypoint]) -> Route:
        """
        Create a complete route from waypoints with calculated segments.
        
        Args:
            waypoints: List of waypoints
            
        Returns:
            Complete route with segments and metadata
            
        Raises:
            ValidationError: If waypoints are invalid
        """
        if not waypoints:
            raise ValidationError("Cannot create route from empty waypoint list")
        
        # Sort waypoints chronologically
        sorted_waypoints, was_reordered = self.sort_waypoints_chronologically(waypoints)
        
        if was_reordered:
            print("Warning: Waypoints were reordered chronologically")
        
        # Calculate route segments
        segments = self.calculate_route_segments(sorted_waypoints)
        
        # Calculate total distance and duration
        total_distance = sum(segment.distance_km for segment in segments)
        total_duration = sum((segment.estimated_duration for segment in segments), timedelta())
        
        # Determine start and end dates
        start_date = sorted_waypoints[0].timestamp
        end_date = sorted_waypoints[-1].timestamp
        
        return Route(
            waypoints=sorted_waypoints,
            segments=segments,
            total_distance_km=total_distance,
            total_duration=total_duration,
            start_date=start_date,
            end_date=end_date
        )
    
    def _validate_chronological_order(self, waypoints: List[Waypoint]) -> None:
        """
        Validate that waypoints are in chronological order.
        
        Args:
            waypoints: List of waypoints to validate
            
        Raises:
            ValidationError: If waypoints are not chronologically ordered
        """
        for i in range(1, len(waypoints)):
            if waypoints[i].timestamp < waypoints[i-1].timestamp:
                raise ValidationError(
                    f"Waypoints must be chronologically ordered. "
                    f"Waypoint {i} ({waypoints[i].location_name}) at {waypoints[i].timestamp} "
                    f"is before waypoint {i-1} ({waypoints[i-1].location_name}) at {waypoints[i-1].timestamp}"
                )
    
    def _validate_waypoint_bounds(self, waypoints: List[Waypoint]) -> None:
        """
        Validate that all waypoints are within reasonable geographic bounds.
        
        Args:
            waypoints: List of waypoints to validate
            
        Raises:
            ValidationError: If any waypoint is out of bounds
        """
        errors = self.validate_waypoints_bounds(waypoints)
        if errors:
            raise ValidationError(f"Invalid waypoint coordinates: {'; '.join(errors)}")
    
    def _calculate_single_segment(self, start: Waypoint, end: Waypoint) -> RouteSegment:
        """
        Calculate a single route segment between two waypoints using OSRM.
        
        Args:
            start: Starting waypoint
            end: Ending waypoint
            
        Returns:
            Route segment with calculated path and distance
            
        Raises:
            Exception: If routing request fails
        """
        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        
        # Build OSRM request URL
        url = f"{self.routing_base_url}/{start.longitude},{start.latitude};{end.longitude},{end.latitude}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "false"
        }
        
        headers = {
            "User-Agent": self.user_agent
        }
        
        # Make request
        response = requests.get(url, params=params, headers=headers, timeout=30)
        self.last_request_time = time.time()
        
        if response.status_code != 200:
            raise Exception(f"OSRM routing request failed with status {response.status_code}: {response.text}")
        
        data = response.json()
        
        if data.get("code") != "Ok":
            raise Exception(f"OSRM routing failed: {data.get('message', 'Unknown error')}")
        
        if not data.get("routes"):
            raise Exception("No routes returned from OSRM")
        
        route_data = data["routes"][0]
        
        # Extract path coordinates from geometry
        geometry = route_data["geometry"]["coordinates"]
        path_coordinates = [Coordinates(lat=coord[1], longitude=coord[0]) for coord in geometry]
        
        # Extract distance (convert from meters to kilometers)
        distance_km = route_data["distance"] / 1000.0
        
        # Extract duration (convert from seconds to timedelta)
        duration_seconds = route_data["duration"]
        estimated_duration = timedelta(seconds=duration_seconds)
        
        return RouteSegment(
            start_waypoint=start,
            end_waypoint=end,
            path_coordinates=path_coordinates,
            distance_km=distance_km,
            estimated_duration=estimated_duration,
            is_custom_route=False
        )
    
    def _create_fallback_segment(self, start: Waypoint, end: Waypoint) -> RouteSegment:
        """
        Create a fallback route segment with straight-line path when routing fails.
        
        Args:
            start: Starting waypoint
            end: Ending waypoint
            
        Returns:
            Route segment with straight-line path
        """
        # Create straight-line path with just start and end points
        path_coordinates = [
            Coordinates(start.latitude, start.longitude),
            Coordinates(end.latitude, end.longitude)
        ]
        
        # Calculate straight-line distance using haversine formula
        distance_km = self._calculate_haversine_distance(
            start.latitude, start.longitude,
            end.latitude, end.longitude
        )
        
        # Estimate duration assuming 60 km/h average speed
        estimated_duration = timedelta(hours=distance_km / 60.0)
        
        return RouteSegment(
            start_waypoint=start,
            end_waypoint=end,
            path_coordinates=path_coordinates,
            distance_km=distance_km,
            estimated_duration=estimated_duration,
            is_custom_route=False
        )
    
    def _calculate_haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points on Earth using the haversine formula.
        
        Args:
            lat1, lon1: Latitude and longitude of first point in decimal degrees
            lat2, lon2: Latitude and longitude of second point in decimal degrees
            
        Returns:
            Distance in kilometers
        """
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Radius of Earth in kilometers
        r = 6371
        
        return c * r
    
    def apply_custom_routing(self, 
                           waypoints: List[Waypoint], 
                           custom_route_overrides: Dict[int, List[Coordinates]]) -> List[RouteSegment]:
        """
        Calculate route segments with custom route overrides for specific segments.
        
        Args:
            waypoints: List of waypoints (must be chronologically ordered)
            custom_route_overrides: Dict mapping segment indices to custom path coordinates
            
        Returns:
            List of route segments with custom overrides applied
            
        Raises:
            ValidationError: If waypoints or custom routes are invalid
        """
        if not waypoints:
            raise ValidationError("Cannot calculate route segments for empty waypoint list")
        
        if len(waypoints) < 2:
            return []  # Single waypoint has no segments
        
        # Validate waypoints are chronologically ordered
        self._validate_chronological_order(waypoints)
        
        # Validate all waypoints are within reasonable bounds
        self._validate_waypoint_bounds(waypoints)
        
        segments = []
        for i in range(len(waypoints) - 1):
            start_waypoint = waypoints[i]
            end_waypoint = waypoints[i + 1]
            
            # Check if this segment has a custom route override
            if i in custom_route_overrides:
                custom_path = custom_route_overrides[i]
                try:
                    segment = self.custom_route_manager.create_custom_route_segment(
                        start_waypoint, end_waypoint, custom_path
                    )
                    segments.append(segment)
                except ValidationError as e:
                    raise ValidationError(f"Custom route override for segment {i} is invalid: {e}")
            else:
                # Use automatic routing
                try:
                    segment = self._calculate_single_segment(start_waypoint, end_waypoint)
                    segments.append(segment)
                except Exception as e:
                    # If routing fails, create a fallback segment with straight-line path
                    fallback_segment = self._create_fallback_segment(start_waypoint, end_waypoint)
                    segments.append(fallback_segment)
                    print(f"Warning: Routing failed for segment {i}, using fallback: {e}")
        
        return segments
    
    def create_route_with_custom_overrides(self, 
                                         waypoints: List[Waypoint],
                                         custom_route_overrides: Optional[Dict[int, List[Coordinates]]] = None) -> Route:
        """
        Create a complete route from waypoints with optional custom route overrides.
        
        Args:
            waypoints: List of waypoints
            custom_route_overrides: Optional dict mapping segment indices to custom paths
            
        Returns:
            Complete route with segments and metadata
            
        Raises:
            ValidationError: If waypoints or custom routes are invalid
        """
        if not waypoints:
            raise ValidationError("Cannot create route from empty waypoint list")
        
        # Sort waypoints chronologically
        sorted_waypoints, was_reordered = self.sort_waypoints_chronologically(waypoints)
        
        if was_reordered:
            print("Warning: Waypoints were reordered chronologically")
        
        # Calculate route segments with custom overrides
        if custom_route_overrides:
            segments = self.apply_custom_routing(sorted_waypoints, custom_route_overrides)
        else:
            segments = self.calculate_route_segments(sorted_waypoints)
        
        # Calculate total distance and duration
        total_distance = sum(segment.distance_km for segment in segments)
        total_duration = sum((segment.estimated_duration for segment in segments), timedelta())
        
        # Determine start and end dates
        start_date = sorted_waypoints[0].timestamp
        end_date = sorted_waypoints[-1].timestamp
        
        return Route(
            waypoints=sorted_waypoints,
            segments=segments,
            total_distance_km=total_distance,
            total_duration=total_duration,
            start_date=start_date,
            end_date=end_date
        )
    
    def validate_custom_route_overrides(self, 
                                      waypoints: List[Waypoint],
                                      custom_route_overrides: Dict[int, List[Coordinates]]) -> List[str]:
        """
        Validate custom route overrides connect properly to adjacent waypoints.
        
        Args:
            waypoints: List of waypoints
            custom_route_overrides: Dict mapping segment indices to custom paths
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if not waypoints or len(waypoints) < 2:
            return errors
        
        max_segment_index = len(waypoints) - 2  # n waypoints = n-1 segments
        
        for segment_index, custom_path in custom_route_overrides.items():
            # Validate segment index is valid
            if segment_index < 0 or segment_index > max_segment_index:
                errors.append(f"Invalid segment index {segment_index}. Must be between 0 and {max_segment_index}")
                continue
            
            # Validate custom path
            if not custom_path or len(custom_path) < 2:
                errors.append(f"Custom path for segment {segment_index} must have at least 2 coordinates")
                continue
            
            # Get expected start and end waypoints
            start_waypoint = waypoints[segment_index]
            end_waypoint = waypoints[segment_index + 1]
            
            # Validate path endpoints
            try:
                self.custom_route_manager._validate_path_endpoints(
                    custom_path, start_waypoint, end_waypoint
                )
            except ValidationError as e:
                errors.append(f"Segment {segment_index}: {e}")
        
        return errors
    
    def get_route_visualization_info(self, segments: List[RouteSegment]) -> Dict[str, Any]:
        """
        Get visualization information for route segments showing automatic vs custom routing.
        
        Args:
            segments: List of route segments
            
        Returns:
            Dictionary with visualization information
        """
        return self.custom_route_manager.get_route_type_indicators(segments)