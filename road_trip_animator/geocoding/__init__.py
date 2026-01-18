"""
Geocoding services for the Road Trip Animator.

This module provides geocoding functionality to convert location names to coordinates
using external services like Nominatim, with caching and error handling.
"""

from .service import GeocodingService, GeocodingResult, LocationContext, FailedGeocoding
from .interactive import InteractiveGeocodingCorrector, ManualCoordinateInput
from .batch import BatchGeocodingProcessor, BatchProcessingConfig, BatchProcessingState

__all__ = [
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