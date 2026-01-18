"""
Core data models for the Road Trip Animator.

This module defines all the data structures used throughout the road trip animation system,
including waypoints, routes, animation frames, layers, and configuration models.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Dict, Tuple, Any
import json
import re


class GranularityLevel(Enum):
    """Geographic detail levels for map generation."""
    COUNTRY = "country"
    STATE = "state"
    REGION = "region"
    CITY = "city"


class LayerType(Enum):
    """Types of visual layers in the animation system."""
    BASE = "base"
    LABELS = "labels"
    TITLE = "title"
    ROUTE = "route"


@dataclass
class Coordinates:
    """Geographic coordinates with validation."""
    latitude: float
    longitude: float
    
    def __post_init__(self):
        """Validate coordinate ranges."""
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Latitude must be between -90 and 90, got {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Longitude must be between -180 and 180, got {self.longitude}")


@dataclass
class Waypoint:
    """A geographic location with timestamp in a trip route."""
    latitude: float
    longitude: float
    timestamp: datetime
    location_name: str
    state: Optional[str] = None
    region: Optional[str] = None
    accommodation: Optional[str] = None
    notes: Optional[str] = None
    
    def __post_init__(self):
        """Validate waypoint data."""
        # Validate coordinates
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Latitude must be between -90 and 90, got {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Longitude must be between -180 and 180, got {self.longitude}")
        
        # Validate location name is not empty
        if not self.location_name or not self.location_name.strip():
            raise ValueError("Location name cannot be empty")
        
        # Validate timestamp is a datetime object
        if not isinstance(self.timestamp, datetime):
            raise ValueError("Timestamp must be a datetime object")
    
    @property
    def coordinates(self) -> Coordinates:
        """Get coordinates as a Coordinates object."""
        return Coordinates(self.latitude, self.longitude)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert waypoint to dictionary for JSON serialization."""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp.isoformat(),
            "location_name": self.location_name,
            "state": self.state,
            "region": self.region,
            "accommodation": self.accommodation,
            "notes": self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Waypoint':
        """Create waypoint from dictionary."""
        return cls(
            latitude=data["latitude"],
            longitude=data["longitude"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            location_name=data["location_name"],
            state=data.get("state"),
            region=data.get("region"),
            accommodation=data.get("accommodation"),
            notes=data.get("notes")
        )


@dataclass
class RouteSegment:
    """The path between two consecutive waypoints in a trip route."""
    start_waypoint: Waypoint
    end_waypoint: Waypoint
    path_coordinates: List[Coordinates]
    distance_km: float
    estimated_duration: timedelta
    is_custom_route: bool = False
    
    def __post_init__(self):
        """Validate route segment data."""
        # Validate distance is positive
        if self.distance_km < 0:
            raise ValueError(f"Distance must be non-negative, got {self.distance_km}")
        
        # Validate duration is positive
        if self.estimated_duration.total_seconds() < 0:
            raise ValueError("Estimated duration must be non-negative")
        
        # Validate path coordinates exist
        if not self.path_coordinates:
            raise ValueError("Path coordinates cannot be empty")
        
        # Validate start and end waypoints are different
        if (self.start_waypoint.latitude == self.end_waypoint.latitude and 
            self.start_waypoint.longitude == self.end_waypoint.longitude):
            raise ValueError("Start and end waypoints cannot be the same location")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert route segment to dictionary for JSON serialization."""
        return {
            "start_waypoint": self.start_waypoint.to_dict(),
            "end_waypoint": self.end_waypoint.to_dict(),
            "path_coordinates": [{"latitude": c.latitude, "longitude": c.longitude} 
                               for c in self.path_coordinates],
            "distance_km": self.distance_km,
            "estimated_duration": self.estimated_duration.total_seconds(),
            "is_custom_route": self.is_custom_route
        }


@dataclass
class Route:
    """A sequence of geographic waypoints with associated timestamps representing a journey."""
    waypoints: List[Waypoint]
    segments: List[RouteSegment]
    total_distance_km: float
    total_duration: timedelta
    start_date: datetime
    end_date: datetime
    
    def __post_init__(self):
        """Validate route data."""
        # Validate waypoints exist
        if not self.waypoints:
            raise ValueError("Route must have at least one waypoint")
        
        # Validate segments match waypoints (n waypoints = n-1 segments)
        if len(self.waypoints) > 1 and len(self.segments) != len(self.waypoints) - 1:
            raise ValueError(f"Expected {len(self.waypoints) - 1} segments for {len(self.waypoints)} waypoints, got {len(self.segments)}")
        
        # Validate total distance matches sum of segment distances
        if self.segments:
            calculated_distance = sum(segment.distance_km for segment in self.segments)
            if abs(self.total_distance_km - calculated_distance) > 0.1:  # Allow small floating point differences
                raise ValueError(f"Total distance {self.total_distance_km} doesn't match sum of segments {calculated_distance}")
        
        # Validate date range
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")
        
        # Validate waypoints are chronologically ordered
        for i in range(1, len(self.waypoints)):
            if self.waypoints[i].timestamp < self.waypoints[i-1].timestamp:
                raise ValueError(f"Waypoints must be chronologically ordered. Waypoint {i} is before waypoint {i-1}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert route to dictionary for JSON serialization."""
        return {
            "waypoints": [wp.to_dict() for wp in self.waypoints],
            "segments": [seg.to_dict() for seg in self.segments],
            "total_distance_km": self.total_distance_km,
            "total_duration": self.total_duration.total_seconds(),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat()
        }


@dataclass
class AnimationFrame:
    """A single PNG image in the animation sequence showing trip progress at a specific time."""
    timestamp: datetime
    current_position: Coordinates
    completed_segments: List[RouteSegment]
    remaining_segments: List[RouteSegment]
    cumulative_distance: float
    days_elapsed: int
    current_location: str
    current_state: str
    
    def __post_init__(self):
        """Validate animation frame data."""
        # Validate cumulative distance is non-negative
        if self.cumulative_distance < 0:
            raise ValueError(f"Cumulative distance must be non-negative, got {self.cumulative_distance}")
        
        # Validate days elapsed is non-negative
        if self.days_elapsed < 0:
            raise ValueError(f"Days elapsed must be non-negative, got {self.days_elapsed}")
        
        # Validate location name is not empty
        if not self.current_location or not self.current_location.strip():
            raise ValueError("Current location cannot be empty")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert animation frame to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "current_position": {
                "latitude": self.current_position.latitude,
                "longitude": self.current_position.longitude
            },
            "completed_segments": [seg.to_dict() for seg in self.completed_segments],
            "remaining_segments": [seg.to_dict() for seg in self.remaining_segments],
            "cumulative_distance": self.cumulative_distance,
            "days_elapsed": self.days_elapsed,
            "current_location": self.current_location,
            "current_state": self.current_state
        }


@dataclass
class Layer:
    """Separate PNG files for different visual elements that can be composited in video editing."""
    layer_type: LayerType
    file_path: str
    timestamp: Optional[datetime]
    description: str
    dependencies: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate layer data."""
        # Validate file path is not empty
        if not self.file_path or not self.file_path.strip():
            raise ValueError("File path cannot be empty")
        
        # Validate description is not empty
        if not self.description or not self.description.strip():
            raise ValueError("Description cannot be empty")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert layer to dictionary for JSON serialization."""
        return {
            "layer_type": self.layer_type.value,
            "file_path": self.file_path,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "description": self.description,
            "dependencies": self.dependencies
        }


@dataclass
class RouteColorScheme:
    """Color scheme for route visualization."""
    completed_route: str = "#FF6B6B"
    remaining_route: str = "#4ECDC4"
    current_position: str = "#FFE66D"
    extended_stay: str = "#A8E6CF"
    
    def __post_init__(self):
        """Validate color scheme."""
        colors = [self.completed_route, self.remaining_route, self.current_position, self.extended_stay]
        for color in colors:
            if not self._is_valid_color(color):
                raise ValueError(f"Invalid color format: {color}")
    
    def _is_valid_color(self, color: str) -> bool:
        """Validate hex color format."""
        if not isinstance(color, str):
            return False
        # Check for hex color format (#RRGGBB or #RGB)
        hex_pattern = re.compile(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
        return bool(hex_pattern.match(color))


@dataclass
class AnimationConfig:
    """Configuration for animation generation."""
    frame_interval: timedelta
    output_resolution: Tuple[int, int]
    theme_name: str
    granularity_level: GranularityLevel
    include_labels: bool = True
    include_titles: bool = True
    route_colors: Optional[RouteColorScheme] = None
    
    def __post_init__(self):
        """Validate animation configuration."""
        # Validate frame interval is positive
        if self.frame_interval.total_seconds() <= 0:
            raise ValueError("Frame interval must be positive")
        
        # Validate output resolution
        width, height = self.output_resolution
        if width <= 0 or height <= 0:
            raise ValueError(f"Output resolution must be positive, got {self.output_resolution}")
        
        # Validate theme name is not empty
        if not self.theme_name or not self.theme_name.strip():
            raise ValueError("Theme name cannot be empty")
        
        # Set default route colors if not provided
        if self.route_colors is None:
            self.route_colors = RouteColorScheme()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert animation config to dictionary for JSON serialization."""
        return {
            "frame_interval": self.frame_interval.total_seconds(),
            "output_resolution": list(self.output_resolution),
            "theme_name": self.theme_name,
            "granularity_level": self.granularity_level.value,
            "include_labels": self.include_labels,
            "include_titles": self.include_titles,
            "route_colors": {
                "completed_route": self.route_colors.completed_route,
                "remaining_route": self.route_colors.remaining_route,
                "current_position": self.route_colors.current_position,
                "extended_stay": self.route_colors.extended_stay
            } if self.route_colors else None
        }


@dataclass
class ProcessingStep:
    """A discrete step in the processing workflow."""
    step_id: str
    name: str
    estimated_duration: timedelta
    dependencies: List[str] = field(default_factory=list)
    validation_required: bool = True
    
    def __post_init__(self):
        """Validate processing step data."""
        # Validate step_id is not empty
        if not self.step_id or not self.step_id.strip():
            raise ValueError("Step ID cannot be empty")
        
        # Validate name is not empty
        if not self.name or not self.name.strip():
            raise ValueError("Step name cannot be empty")
        
        # Validate estimated duration is positive
        if self.estimated_duration.total_seconds() <= 0:
            raise ValueError("Estimated duration must be positive")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert processing step to dictionary for JSON serialization."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "estimated_duration": self.estimated_duration.total_seconds(),
            "dependencies": self.dependencies,
            "validation_required": self.validation_required
        }


@dataclass
class ProcessingPlan:
    """A complete processing plan with steps and timing estimates."""
    steps: List[ProcessingStep]
    total_estimated_time: timedelta
    checkpoint_intervals: List[str] = field(default_factory=list)
    preview_steps: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate processing plan data."""
        # Validate steps exist
        if not self.steps:
            raise ValueError("Processing plan must have at least one step")
        
        # Validate total estimated time matches sum of step durations
        calculated_time = sum((step.estimated_duration for step in self.steps), timedelta())
        if abs((self.total_estimated_time - calculated_time).total_seconds()) > 1:  # Allow 1 second difference
            raise ValueError(f"Total estimated time {self.total_estimated_time} doesn't match sum of steps {calculated_time}")
        
        # Validate checkpoint intervals reference valid step IDs
        step_ids = {step.step_id for step in self.steps}
        for checkpoint in self.checkpoint_intervals:
            if checkpoint not in step_ids:
                raise ValueError(f"Checkpoint interval '{checkpoint}' references unknown step ID")
        
        # Validate preview steps reference valid step IDs
        for preview_step in self.preview_steps:
            if preview_step not in step_ids:
                raise ValueError(f"Preview step '{preview_step}' references unknown step ID")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert processing plan to dictionary for JSON serialization."""
        return {
            "steps": [step.to_dict() for step in self.steps],
            "total_estimated_time": self.total_estimated_time.total_seconds(),
            "checkpoint_intervals": self.checkpoint_intervals,
            "preview_steps": self.preview_steps
        }


@dataclass
class PreviewFrame:
    """Low-fidelity preview frame for rapid validation."""
    timestamp: datetime
    low_res_image_path: str
    validation_status: str
    issues_detected: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate preview frame data."""
        # Validate image path is not empty
        if not self.low_res_image_path or not self.low_res_image_path.strip():
            raise ValueError("Image path cannot be empty")
        
        # Validate validation status is not empty
        if not self.validation_status or not self.validation_status.strip():
            raise ValueError("Validation status cannot be empty")


@dataclass
class RouteBuffer:
    """Route-focused data acquisition configuration."""
    waypoints: List[Waypoint]
    buffer_distance_km: float
    bounding_box: Tuple[float, float, float, float]  # (min_lat, min_lon, max_lat, max_lon)
    estimated_data_size_mb: float
    
    def __post_init__(self):
        """Validate route buffer data."""
        # Validate waypoints exist
        if not self.waypoints:
            raise ValueError("Route buffer must have at least one waypoint")
        
        # Validate buffer distance is positive
        if self.buffer_distance_km <= 0:
            raise ValueError(f"Buffer distance must be positive, got {self.buffer_distance_km}")
        
        # Validate bounding box
        min_lat, min_lon, max_lat, max_lon = self.bounding_box
        if min_lat >= max_lat:
            raise ValueError("Minimum latitude must be less than maximum latitude")
        if min_lon >= max_lon:
            raise ValueError("Minimum longitude must be less than maximum longitude")
        
        # Validate estimated data size is non-negative
        if self.estimated_data_size_mb < 0:
            raise ValueError(f"Estimated data size must be non-negative, got {self.estimated_data_size_mb}")


@dataclass
class ZoomKeyframe:
    """Keyframe for dynamic zoom control during animation."""
    timestamp: datetime
    zoom_level: float  # Map scale (e.g., 1:50000 = 50000.0)
    center_point: Coordinates
    transition_duration: timedelta
    easing_function: str = "ease_in_out"
    
    def __post_init__(self):
        """Validate zoom keyframe data."""
        # Validate zoom level is positive
        if self.zoom_level <= 0:
            raise ValueError(f"Zoom level must be positive, got {self.zoom_level}")
        
        # Validate transition duration is non-negative
        if self.transition_duration.total_seconds() < 0:
            raise ValueError("Transition duration must be non-negative")
        
        # Validate easing function
        valid_easing = ["linear", "ease_in", "ease_out", "ease_in_out"]
        if self.easing_function not in valid_easing:
            raise ValueError(f"Easing function must be one of {valid_easing}, got {self.easing_function}")


@dataclass
class ZoomConfiguration:
    """Configuration for dynamic zoom animation."""
    keyframes: List[ZoomKeyframe]
    default_zoom_level: float
    min_zoom_level: float
    max_zoom_level: float
    auto_zoom_to_route: bool = True
    
    def __post_init__(self):
        """Validate zoom configuration."""
        # Validate zoom levels are positive
        if self.default_zoom_level <= 0:
            raise ValueError(f"Default zoom level must be positive, got {self.default_zoom_level}")
        if self.min_zoom_level <= 0:
            raise ValueError(f"Minimum zoom level must be positive, got {self.min_zoom_level}")
        if self.max_zoom_level <= 0:
            raise ValueError(f"Maximum zoom level must be positive, got {self.max_zoom_level}")
        
        # Validate zoom level relationships
        if self.min_zoom_level >= self.max_zoom_level:
            raise ValueError("Minimum zoom level must be less than maximum zoom level")
        if not self.min_zoom_level <= self.default_zoom_level <= self.max_zoom_level:
            raise ValueError("Default zoom level must be between minimum and maximum zoom levels")
        
        # Validate keyframes are chronologically ordered
        for i in range(1, len(self.keyframes)):
            if self.keyframes[i].timestamp < self.keyframes[i-1].timestamp:
                raise ValueError(f"Keyframes must be chronologically ordered. Keyframe {i} is before keyframe {i-1}")


@dataclass
class MultiScaleFrame:
    """Animation frame with multi-scale rendering information."""
    timestamp: datetime
    current_zoom_level: float
    center_point: Coordinates
    visible_bounds: Tuple[float, float, float, float]  # (min_lat, min_lon, max_lat, max_lon)
    required_data_detail_level: str
    frame_layers: Dict[str, str] = field(default_factory=dict)  # layer_type -> file_path
    
    def __post_init__(self):
        """Validate multi-scale frame data."""
        # Validate zoom level is positive
        if self.current_zoom_level <= 0:
            raise ValueError(f"Zoom level must be positive, got {self.current_zoom_level}")
        
        # Validate visible bounds
        min_lat, min_lon, max_lat, max_lon = self.visible_bounds
        if min_lat >= max_lat:
            raise ValueError("Minimum latitude must be less than maximum latitude")
        if min_lon >= max_lon:
            raise ValueError("Minimum longitude must be less than maximum longitude")
        
        # Validate required data detail level
        valid_levels = ["country", "state", "region", "city", "street"]
        if self.required_data_detail_level not in valid_levels:
            raise ValueError(f"Required data detail level must be one of {valid_levels}, got {self.required_data_detail_level}")