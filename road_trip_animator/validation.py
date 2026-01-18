"""
Validation utilities for the Road Trip Animator.

This module provides validation functions and utilities used throughout
the road trip animation system to ensure data integrity and correctness.
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from .models import Waypoint, RouteSegment, Route


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


def validate_coordinate_range(latitude: float, longitude: float) -> None:
    """
    Validate that coordinates are within valid ranges.
    
    Args:
        latitude: Latitude value to validate
        longitude: Longitude value to validate
        
    Raises:
        ValidationError: If coordinates are out of valid range
    """
    if not -90 <= latitude <= 90:
        raise ValidationError(f"Latitude must be between -90 and 90, got {latitude}")
    if not -180 <= longitude <= 180:
        raise ValidationError(f"Longitude must be between -180 and 180, got {longitude}")


def validate_hex_color(color: str) -> bool:
    """
    Validate hex color format.
    
    Args:
        color: Color string to validate
        
    Returns:
        True if valid hex color, False otherwise
    """
    if not isinstance(color, str):
        return False
    # Check for hex color format (#RRGGBB or #RGB)
    hex_pattern = re.compile(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
    return bool(hex_pattern.match(color))


def validate_waypoint_chronology(waypoints: List[Waypoint]) -> List[str]:
    """
    Validate that waypoints are in chronological order.
    
    Args:
        waypoints: List of waypoints to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if len(waypoints) < 2:
        return errors
    
    for i in range(1, len(waypoints)):
        if waypoints[i].timestamp < waypoints[i-1].timestamp:
            errors.append(
                f"Waypoint {i} ({waypoints[i].location_name}) at {waypoints[i].timestamp} "
                f"is before waypoint {i-1} ({waypoints[i-1].location_name}) at {waypoints[i-1].timestamp}"
            )
    
    return errors


def validate_route_segments_match_waypoints(waypoints: List[Waypoint], segments: List[RouteSegment]) -> List[str]:
    """
    Validate that route segments properly connect waypoints.
    
    Args:
        waypoints: List of waypoints
        segments: List of route segments
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if len(waypoints) <= 1:
        if segments:
            errors.append("Route with single waypoint should not have segments")
        return errors
    
    expected_segments = len(waypoints) - 1
    if len(segments) != expected_segments:
        errors.append(f"Expected {expected_segments} segments for {len(waypoints)} waypoints, got {len(segments)}")
        return errors
    
    # Validate each segment connects consecutive waypoints
    for i, segment in enumerate(segments):
        start_wp = waypoints[i]
        end_wp = waypoints[i + 1]
        
        # Check start waypoint matches
        if (abs(segment.start_waypoint.latitude - start_wp.latitude) > 0.0001 or
            abs(segment.start_waypoint.longitude - start_wp.longitude) > 0.0001):
            errors.append(f"Segment {i} start waypoint doesn't match waypoint {i}")
        
        # Check end waypoint matches
        if (abs(segment.end_waypoint.latitude - end_wp.latitude) > 0.0001 or
            abs(segment.end_waypoint.longitude - end_wp.longitude) > 0.0001):
            errors.append(f"Segment {i} end waypoint doesn't match waypoint {i+1}")
    
    return errors


def validate_distance_consistency(segments: List[RouteSegment], total_distance: float) -> List[str]:
    """
    Validate that total distance matches sum of segment distances.
    
    Args:
        segments: List of route segments
        total_distance: Claimed total distance
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if not segments:
        if total_distance != 0:
            errors.append(f"Route with no segments should have zero distance, got {total_distance}")
        return errors
    
    calculated_distance = sum(segment.distance_km for segment in segments)
    if abs(total_distance - calculated_distance) > 0.1:  # Allow small floating point differences
        errors.append(
            f"Total distance {total_distance} km doesn't match sum of segments {calculated_distance} km "
            f"(difference: {abs(total_distance - calculated_distance):.3f} km)"
        )
    
    return errors


def validate_bounding_box(bounding_box: Tuple[float, float, float, float]) -> List[str]:
    """
    Validate bounding box coordinates.
    
    Args:
        bounding_box: Tuple of (min_lat, min_lon, max_lat, max_lon)
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    min_lat, min_lon, max_lat, max_lon = bounding_box
    
    # Validate coordinate ranges
    try:
        validate_coordinate_range(min_lat, min_lon)
        validate_coordinate_range(max_lat, max_lon)
    except ValidationError as e:
        errors.append(str(e))
    
    # Validate min < max relationships
    if min_lat >= max_lat:
        errors.append(f"Minimum latitude {min_lat} must be less than maximum latitude {max_lat}")
    if min_lon >= max_lon:
        errors.append(f"Minimum longitude {min_lon} must be less than maximum longitude {max_lon}")
    
    return errors


def validate_file_path(file_path: str, allow_empty: bool = False) -> List[str]:
    """
    Validate file path format.
    
    Args:
        file_path: File path to validate
        allow_empty: Whether to allow empty file paths
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if not file_path or not file_path.strip():
        if not allow_empty:
            errors.append("File path cannot be empty")
        return errors
    
    # Check for invalid characters (basic validation)
    invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
    for char in invalid_chars:
        if char in file_path:
            errors.append(f"File path contains invalid character: {char}")
    
    return errors


def validate_positive_duration(duration: timedelta, field_name: str = "duration") -> List[str]:
    """
    Validate that a duration is positive.
    
    Args:
        duration: Duration to validate
        field_name: Name of the field for error messages
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if duration.total_seconds() <= 0:
        errors.append(f"{field_name} must be positive, got {duration}")
    
    return errors


def validate_non_negative_number(value: float, field_name: str = "value") -> List[str]:
    """
    Validate that a number is non-negative.
    
    Args:
        value: Number to validate
        field_name: Name of the field for error messages
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if value < 0:
        errors.append(f"{field_name} must be non-negative, got {value}")
    
    return errors


def validate_resolution(resolution: Tuple[int, int]) -> List[str]:
    """
    Validate output resolution.
    
    Args:
        resolution: Tuple of (width, height)
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    width, height = resolution
    
    if width <= 0:
        errors.append(f"Width must be positive, got {width}")
    if height <= 0:
        errors.append(f"Height must be positive, got {height}")
    
    # Check for reasonable resolution limits
    if width > 10000 or height > 10000:
        errors.append(f"Resolution {width}x{height} may be too large for practical use")
    
    return errors


def validate_non_empty_string(value: str, field_name: str = "string") -> List[str]:
    """
    Validate that a string is not empty or whitespace-only.
    
    Args:
        value: String to validate
        field_name: Name of the field for error messages
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if not value or not value.strip():
        errors.append(f"{field_name} cannot be empty")
    
    return errors