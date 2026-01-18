"""
Road Trip Animator - A module for creating animated visualizations of road trips.

This module extends the existing map poster system to create animated visualizations
of road trips for video production workflows.
"""

from .models import (
    Waypoint,
    RouteSegment,
    Route,
    AnimationFrame,
    Layer,
    AnimationConfig,
    ZoomConfiguration,
    ProcessingPlan,
    GranularityLevel,
    LayerType,
    RouteColorScheme,
    ProcessingStep,
    PreviewFrame,
    RouteBuffer,
    ZoomKeyframe,
    MultiScaleFrame
)

from .geocoding import (
    GeocodingService,
    GeocodingResult,
    LocationContext,
    FailedGeocoding,
    InteractiveGeocodingCorrector,
    ManualCoordinateInput,
    BatchGeocodingProcessor,
    BatchProcessingConfig,
    BatchProcessingState
)

__version__ = "0.1.0"
__all__ = [
    "Waypoint",
    "RouteSegment", 
    "Route",
    "AnimationFrame",
    "Layer",
    "AnimationConfig",
    "ZoomConfiguration",
    "ProcessingPlan",
    "GranularityLevel",
    "LayerType",
    "RouteColorScheme",
    "ProcessingStep",
    "PreviewFrame",
    "RouteBuffer",
    "ZoomKeyframe",
    "MultiScaleFrame",
    "GeocodingService",
    "GeocodingResult",
    "LocationContext",
    "FailedGeocoding",
    "InteractiveGeocodingCorrector",
    "ManualCoordinateInput",
    "BatchGeocodingProcessor",
    "BatchProcessingConfig",
    "BatchProcessingState"
]