"""
Custom route override functionality for the Road Trip Animator.

This module provides capabilities for users to define custom route segments
with intermediate waypoints and validate that they connect properly.
"""

import math
from datetime import timedelta
from typing import List, Optional, Dict, Any, Tuple
from ..models import Waypoint, RouteSegment, Coordinates
from ..validation import ValidationError, validate_coordinate_range


class CustomRouteManager:
    """
    Manages custom route overrides and validation.
    
    This class handles user-defined route segments, validates connectivity,
    and provides visual feedback for automatic vs custom routing segments.
    """
    
    def __init__(self):
        """Initialize the custom route manager."""
        self.custom_segments: Dict[str, List[Coordinates]] = {}
    
    def add_custom_route_segment(self, 
                                start_waypoint: Waypoint, 
                                end_waypoint: Waypoint,
                                intermediate_waypoints: List[Coordinates],
                                segment_id: Optional[str] = None) -> str:
        """
        Add a custom route segment with intermediate waypoints.
        
        Args:
            start_waypoint: Starting waypoint
            end_waypoint: Ending waypoint
            intermediate_waypoints: List of intermediate coordinates along the route
            segment_id: Optional custom ID for the segment
            
        Returns:
            Segment ID for the custom route
            
        Raises:
            ValidationError: If the custom route is invalid
        """
        # Generate segment ID if not provided
        if segment_id is None:
            segment_id = f"custom_{start_waypoint.location_name}_{end_waypoint.location_name}_{len(self.custom_segments)}"
        
        # Validate intermediate waypoints
        self._validate_intermediate_waypoints(intermediate_waypoints)
        
        # Create full path including start, intermediate, and end points
        full_path = [Coordinates(start_waypoint.latitude, start_waypoint.longitude)]
        full_path.extend(intermediate_waypoints)
        full_path.append(Coordinates(end_waypoint.latitude, end_waypoint.longitude))
        
        # Validate connectivity
        self._validate_route_connectivity(full_path, start_waypoint, end_waypoint)
        
        # Store the custom segment
        self.custom_segments[segment_id] = full_path
        
        return segment_id
    
    def create_custom_route_segment(self,
                                   start_waypoint: Waypoint,
                                   end_waypoint: Waypoint,
                                   custom_path: List[Coordinates]) -> RouteSegment:
        """
        Create a RouteSegment with custom path.
        
        Args:
            start_waypoint: Starting waypoint
            end_waypoint: Ending waypoint
            custom_path: Custom path coordinates (including start and end)
            
        Returns:
            RouteSegment with custom path
            
        Raises:
            ValidationError: If the custom route is invalid
        """
        # Validate custom path
        if not custom_path:
            raise ValidationError("Custom path cannot be empty")
        
        if len(custom_path) < 2:
            raise ValidationError("Custom path must have at least 2 points (start and end)")
        
        # Validate that path starts and ends at the correct waypoints
        self._validate_path_endpoints(custom_path, start_waypoint, end_waypoint)
        
        # Calculate distance along the custom path
        distance_km = self._calculate_path_distance(custom_path)
        
        # Estimate duration assuming 50 km/h average speed for custom routes
        estimated_duration = timedelta(hours=distance_km / 50.0)
        
        return RouteSegment(
            start_waypoint=start_waypoint,
            end_waypoint=end_waypoint,
            path_coordinates=custom_path,
            distance_km=distance_km,
            estimated_duration=estimated_duration,
            is_custom_route=True
        )
    
    def validate_custom_route_connectivity(self,
                                         custom_segments: List[RouteSegment],
                                         waypoints: List[Waypoint]) -> List[str]:
        """
        Validate that custom route segments connect properly to adjacent waypoints.
        
        Args:
            custom_segments: List of custom route segments
            waypoints: List of waypoints that should be connected
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if not custom_segments:
            return errors
        
        if len(waypoints) != len(custom_segments) + 1:
            errors.append(f"Expected {len(waypoints) - 1} segments for {len(waypoints)} waypoints, got {len(custom_segments)}")
            return errors
        
        # Check each segment connects to the correct waypoints
        for i, segment in enumerate(custom_segments):
            expected_start = waypoints[i]
            expected_end = waypoints[i + 1]
            
            # Validate start connection
            start_errors = self._validate_waypoint_connection(
                segment.path_coordinates[0], expected_start, f"Segment {i} start"
            )
            errors.extend(start_errors)
            
            # Validate end connection
            end_errors = self._validate_waypoint_connection(
                segment.path_coordinates[-1], expected_end, f"Segment {i} end"
            )
            errors.extend(end_errors)
        
        return errors
    
    def get_route_type_indicators(self, segments: List[RouteSegment]) -> Dict[str, Any]:
        """
        Provide visual feedback for automatic vs custom routing segments.
        
        Args:
            segments: List of route segments
            
        Returns:
            Dictionary with routing type information for visualization
        """
        indicators = {
            "total_segments": len(segments),
            "custom_segments": 0,
            "automatic_segments": 0,
            "segment_types": [],
            "custom_segment_indices": [],
            "automatic_segment_indices": []
        }
        
        for i, segment in enumerate(segments):
            if segment.is_custom_route:
                indicators["custom_segments"] += 1
                indicators["custom_segment_indices"].append(i)
                indicators["segment_types"].append("custom")
            else:
                indicators["automatic_segments"] += 1
                indicators["automatic_segment_indices"].append(i)
                indicators["segment_types"].append("automatic")
        
        # Calculate percentages
        if indicators["total_segments"] > 0:
            indicators["custom_percentage"] = (indicators["custom_segments"] / indicators["total_segments"]) * 100
            indicators["automatic_percentage"] = (indicators["automatic_segments"] / indicators["total_segments"]) * 100
        else:
            indicators["custom_percentage"] = 0
            indicators["automatic_percentage"] = 0
        
        return indicators
    
    def remove_custom_segment(self, segment_id: str) -> bool:
        """
        Remove a custom route segment.
        
        Args:
            segment_id: ID of the segment to remove
            
        Returns:
            True if segment was removed, False if not found
        """
        if segment_id in self.custom_segments:
            del self.custom_segments[segment_id]
            return True
        return False
    
    def list_custom_segments(self) -> List[str]:
        """
        Get list of all custom segment IDs.
        
        Returns:
            List of custom segment IDs
        """
        return list(self.custom_segments.keys())
    
    def get_custom_segment_path(self, segment_id: str) -> Optional[List[Coordinates]]:
        """
        Get the path for a custom segment.
        
        Args:
            segment_id: ID of the segment
            
        Returns:
            List of coordinates for the segment, or None if not found
        """
        return self.custom_segments.get(segment_id)
    
    def _validate_intermediate_waypoints(self, waypoints: List[Coordinates]) -> None:
        """
        Validate intermediate waypoints are within valid coordinate ranges.
        
        Args:
            waypoints: List of intermediate waypoints to validate
            
        Raises:
            ValidationError: If any waypoint is invalid
        """
        for i, waypoint in enumerate(waypoints):
            try:
                validate_coordinate_range(waypoint.latitude, waypoint.longitude)
            except ValidationError as e:
                raise ValidationError(f"Intermediate waypoint {i}: {e}")
    
    def _validate_route_connectivity(self,
                                   full_path: List[Coordinates],
                                   start_waypoint: Waypoint,
                                   end_waypoint: Waypoint) -> None:
        """
        Validate that the route connects the start and end waypoints properly.
        
        Args:
            full_path: Complete path including all coordinates
            start_waypoint: Expected starting waypoint
            end_waypoint: Expected ending waypoint
            
        Raises:
            ValidationError: If connectivity is invalid
        """
        if not full_path:
            raise ValidationError("Route path cannot be empty")
        
        # Check start point
        start_coord = full_path[0]
        if not self._coordinates_match(start_coord, start_waypoint.coordinates, tolerance=0.001):
            raise ValidationError(
                f"Route start point ({start_coord.latitude}, {start_coord.longitude}) "
                f"doesn't match waypoint ({start_waypoint.latitude}, {start_waypoint.longitude})"
            )
        
        # Check end point
        end_coord = full_path[-1]
        if not self._coordinates_match(end_coord, end_waypoint.coordinates, tolerance=0.001):
            raise ValidationError(
                f"Route end point ({end_coord.latitude}, {end_coord.longitude}) "
                f"doesn't match waypoint ({end_waypoint.latitude}, {end_waypoint.longitude})"
            )
    
    def _validate_path_endpoints(self,
                                path: List[Coordinates],
                                start_waypoint: Waypoint,
                                end_waypoint: Waypoint) -> None:
        """
        Validate that path starts and ends at the correct waypoints.
        
        Args:
            path: Path coordinates
            start_waypoint: Expected starting waypoint
            end_waypoint: Expected ending waypoint
            
        Raises:
            ValidationError: If endpoints don't match
        """
        # Check start point (allow small tolerance for coordinate precision)
        start_coord = path[0]
        if abs(start_coord.latitude - start_waypoint.latitude) > 0.001 or \
           abs(start_coord.longitude - start_waypoint.longitude) > 0.001:
            raise ValidationError(
                f"Custom path start ({start_coord.latitude}, {start_coord.longitude}) "
                f"doesn't match start waypoint ({start_waypoint.latitude}, {start_waypoint.longitude})"
            )
        
        # Check end point
        end_coord = path[-1]
        if abs(end_coord.latitude - end_waypoint.latitude) > 0.001 or \
           abs(end_coord.longitude - end_waypoint.longitude) > 0.001:
            raise ValidationError(
                f"Custom path end ({end_coord.latitude}, {end_coord.longitude}) "
                f"doesn't match end waypoint ({end_waypoint.latitude}, {end_waypoint.longitude})"
            )
    
    def _validate_waypoint_connection(self,
                                    path_coord: Coordinates,
                                    waypoint: Waypoint,
                                    context: str) -> List[str]:
        """
        Validate that a path coordinate connects to a waypoint.
        
        Args:
            path_coord: Coordinate from the path
            waypoint: Waypoint to connect to
            context: Context for error messages
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Allow small tolerance for coordinate precision
        tolerance = 0.001
        if abs(path_coord.latitude - waypoint.latitude) > tolerance or \
           abs(path_coord.longitude - waypoint.longitude) > tolerance:
            errors.append(
                f"{context}: path coordinate ({path_coord.latitude}, {path_coord.longitude}) "
                f"doesn't connect to waypoint ({waypoint.latitude}, {waypoint.longitude})"
            )
        
        return errors
    
    def _coordinates_match(self, coord1: Coordinates, coord2: Coordinates, tolerance: float = 0.001) -> bool:
        """
        Check if two coordinates match within a tolerance.
        
        Args:
            coord1: First coordinate
            coord2: Second coordinate
            tolerance: Tolerance for matching
            
        Returns:
            True if coordinates match within tolerance
        """
        return (abs(coord1.latitude - coord2.latitude) <= tolerance and
                abs(coord1.longitude - coord2.longitude) <= tolerance)
    
    def _calculate_path_distance(self, path: List[Coordinates]) -> float:
        """
        Calculate total distance along a path using haversine formula.
        
        Args:
            path: List of coordinates forming the path
            
        Returns:
            Total distance in kilometers
        """
        if len(path) < 2:
            return 0.0
        
        total_distance = 0.0
        for i in range(len(path) - 1):
            current = path[i]
            next_point = path[i + 1]
            
            distance = self._calculate_haversine_distance(
                current.latitude, current.longitude,
                next_point.latitude, next_point.longitude
            )
            total_distance += distance
        
        return total_distance
    
    def _calculate_haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points using the haversine formula.
        
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