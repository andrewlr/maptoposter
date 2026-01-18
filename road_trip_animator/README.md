# Road Trip Animator

A Python module for creating animated visualizations of road trips for video production workflows.

## Overview

The Road Trip Animator extends the existing map poster system to create animated visualizations of road trips. The system generates transparent PNG base maps and creates progressive animations showing trip routes with timestamps, designed specifically for video editing workflows.

## Project Structure

```
road_trip_animator/
├── __init__.py              # Main module exports
├── models.py                # Core data models and validation
├── validation.py            # Validation utilities
├── README.md               # This file
├── data/                   # Data processing components
│   └── __init__.py
├── routing/                # Route calculation components  
│   └── __init__.py
├── animation/              # Animation generation components
│   └── __init__.py
├── cache/                  # Cache management components
│   └── __init__.py
└── processing/             # Processing workflow components
    └── __init__.py
```

## Core Data Models

### Primary Models

- **`Waypoint`**: A geographic location with timestamp in a trip route
- **`RouteSegment`**: The path between two consecutive waypoints
- **`Route`**: A complete sequence of waypoints and segments representing a journey
- **`AnimationFrame`**: A single frame in the animation sequence showing trip progress
- **`Layer`**: Separate PNG files for different visual elements (base, labels, titles, routes)

### Configuration Models

- **`AnimationConfig`**: Configuration for animation generation (resolution, theme, intervals)
- **`ZoomConfiguration`**: Dynamic zoom control with keyframes and transitions
- **`ProcessingPlan`**: Step-by-step processing workflow with time estimates
- **`RouteColorScheme`**: Color scheme for route visualization

### Supporting Models

- **`Coordinates`**: Geographic coordinates with validation
- **`ProcessingStep`**: Individual step in the processing workflow
- **`PreviewFrame`**: Low-fidelity preview for rapid validation
- **`RouteBuffer`**: Route-focused data acquisition configuration
- **`ZoomKeyframe`**: Keyframe for dynamic zoom animation
- **`MultiScaleFrame`**: Animation frame with multi-scale rendering information

## Key Features

### Data Validation

All data models include comprehensive validation:
- Geographic coordinate range validation (-90 to 90 for latitude, -180 to 180 for longitude)
- Chronological ordering of waypoints and keyframes
- Distance and duration consistency checks
- File path and color format validation
- Non-negative values for distances, durations, and counts

### JSON Serialization

Core models support JSON serialization for data persistence:
- `to_dict()` methods for converting to dictionaries
- `from_dict()` class methods for restoration from dictionaries
- ISO format timestamps for datetime objects
- Human-readable JSON output for easy editing

### Granularity Levels

The system supports different levels of geographic detail:
- **Country**: Major highways and interstate roads only
- **State**: Highways and primary roads
- **Region**: Highways, primary, and secondary roads
- **City**: All road types (full detail)

### Layer System

Separate PNG layers for flexible video production:
- **Base Layer**: Geographic features without text or overlays
- **Label Layer**: Place names and points of interest
- **Title Layer**: Date, location, and trip statistics
- **Route Layer**: Trip progress and position markers

## Usage Example

```python
from datetime import datetime, timedelta
from road_trip_animator.models import (
    Waypoint, Route, AnimationConfig, GranularityLevel
)

# Create waypoints
wp1 = Waypoint(
    latitude=-37.8136,
    longitude=144.9631,
    timestamp=datetime(2024, 1, 1, 10, 0),
    location_name="Melbourne",
    state="Victoria"
)

wp2 = Waypoint(
    latitude=-37.7749,
    longitude=144.9441,
    timestamp=datetime(2024, 1, 2, 14, 30),
    location_name="St Kilda",
    state="Victoria"
)

# Create animation configuration
config = AnimationConfig(
    frame_interval=timedelta(hours=1),
    output_resolution=(1920, 1080),
    theme_name="noir",
    granularity_level=GranularityLevel.CITY
)

# Models automatically validate data on creation
print(f"✓ Created waypoint: {wp1.location_name}")
print(f"✓ Created config for {config.output_resolution} resolution")
```

## Requirements Addressed

This implementation addresses the following requirements from the specification:

- **Requirement 8.8**: Data validation and error reporting with specific line numbers
- **Requirement 16.4**: Local storage in human-readable JSON format

## Next Steps

The following components will be implemented in subsequent tasks:

1. **Data Import System**: CSV, GPX, and JSON parsers with geocoding
2. **Route Processing**: OpenStreetMap routing and custom path support
3. **Cache Management**: Hierarchical geographic data caching
4. **Animation Generation**: Frame sequences and layer creation
5. **Processing Workflow**: Incremental processing with validation checkpoints

## Testing

Run the basic test suite to verify the data models:

```bash
python test_data_models.py
```

This test validates:
- Basic model creation and functionality
- Data validation logic
- JSON serialization round-trips
- Error handling for invalid data