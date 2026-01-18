"""
Interactive geocoding correction and user input handling.

This module provides functionality for user interaction when geocoding fails,
including manual coordinate input and batch correction capabilities.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from ..models import Coordinates
from .service import GeocodingService, FailedGeocoding, LocationContext, GeocodingResult


logger = logging.getLogger(__name__)


@dataclass
class ManualCoordinateInput:
    """Manual coordinate input from user."""
    location_name: str
    latitude: float
    longitude: float
    context: Optional[LocationContext] = None
    notes: Optional[str] = None
    
    def to_coordinates(self) -> Coordinates:
        """Convert to Coordinates object."""
        return Coordinates(self.latitude, self.longitude)


class InteractiveGeocodingCorrector:
    """
    Interactive interface for reviewing and correcting failed geocoding attempts.
    
    Provides functionality for:
    - Displaying summary of successful and failed geocoding attempts
    - Manual coordinate specification for failed locations
    - Bulk editing capabilities for systematic error correction
    - Validation of manual coordinate inputs
    """
    
    def __init__(self, geocoding_service: GeocodingService):
        """
        Initialize the interactive corrector.
        
        Args:
            geocoding_service: The geocoding service to work with
        """
        self.geocoding_service = geocoding_service
        self.manual_corrections: List[ManualCoordinateInput] = []
    
    def get_geocoding_summary(self, results: List[GeocodingResult]) -> Dict[str, Any]:
        """
        Generate a summary of geocoding results.
        
        Args:
            results: List of geocoding results to summarize
            
        Returns:
            Dictionary containing summary statistics and details
        """
        total = len(results)
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        # Group failed results by error type
        error_groups: Dict[str, List[GeocodingResult]] = {}
        for result in failed:
            error_type = result.error_message or "Unknown error"
            if error_type not in error_groups:
                error_groups[error_type] = []
            error_groups[error_type].append(result)
        
        # Calculate confidence statistics for successful results
        confidences = [r.confidence for r in successful if r.confidence > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        summary = {
            "total_locations": total,
            "successful_count": len(successful),
            "failed_count": len(failed),
            "success_rate": len(successful) / total if total > 0 else 0.0,
            "average_confidence": avg_confidence,
            "successful_locations": [
                {
                    "location": r.location_name,
                    "coordinates": {
                        "latitude": r.coordinates.latitude,
                        "longitude": r.coordinates.longitude
                    } if r.coordinates else None,
                    "confidence": r.confidence,
                    "display_name": r.display_name
                }
                for r in successful
            ],
            "failed_locations": [
                {
                    "location": r.location_name,
                    "error": r.error_message,
                    "context": {
                        "state": r.context_used.state if r.context_used else None,
                        "region": r.context_used.region if r.context_used else None,
                        "country": r.context_used.country if r.context_used else None
                    }
                }
                for r in failed
            ],
            "error_groups": {
                error_type: len(results)
                for error_type, results in error_groups.items()
            }
        }
        
        logger.info(f"Geocoding summary: {len(successful)}/{total} successful ({summary['success_rate']:.1%})")
        
        return summary
    
    def validate_coordinates(self, latitude: float, longitude: float, 
                           context: Optional[LocationContext] = None) -> Tuple[bool, Optional[str]]:
        """
        Validate that coordinates are reasonable for the specified region.
        
        Args:
            latitude: Latitude to validate
            longitude: Longitude to validate
            context: Optional context for regional validation
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Basic coordinate range validation
        if not -90 <= latitude <= 90:
            return False, f"Latitude {latitude} is outside valid range [-90, 90]"
        
        if not -180 <= longitude <= 180:
            return False, f"Longitude {longitude} is outside valid range [-180, 180]"
        
        # Regional validation if context is provided
        if context:
            # Define rough bounding boxes for common regions
            region_bounds = {
                # US states (rough approximations)
                "california": {"lat_min": 32.5, "lat_max": 42.0, "lon_min": -124.5, "lon_max": -114.1},
                "texas": {"lat_min": 25.8, "lat_max": 36.5, "lon_min": -106.6, "lon_max": -93.5},
                "florida": {"lat_min": 24.4, "lat_max": 31.0, "lon_min": -87.6, "lon_max": -80.0},
                "new york": {"lat_min": 40.5, "lat_max": 45.0, "lon_min": -79.8, "lon_max": -71.9},
                
                # Countries (rough approximations)
                "united states": {"lat_min": 24.4, "lat_max": 71.4, "lon_min": -179.1, "lon_max": -66.9},
                "canada": {"lat_min": 41.7, "lat_max": 83.1, "lon_min": -141.0, "lon_max": -52.6},
                "australia": {"lat_min": -43.6, "lat_max": -10.7, "lon_min": 113.3, "lon_max": 153.6},
                "united kingdom": {"lat_min": 49.9, "lat_max": 60.8, "lon_min": -8.6, "lon_max": 1.8},
            }
            
            # Check against known regions
            for region_key in [context.state, context.region, context.country]:
                if region_key:
                    region_key_lower = region_key.lower()
                    if region_key_lower in region_bounds:
                        bounds = region_bounds[region_key_lower]
                        if not (bounds["lat_min"] <= latitude <= bounds["lat_max"] and
                                bounds["lon_min"] <= longitude <= bounds["lon_max"]):
                            return False, f"Coordinates ({latitude}, {longitude}) appear to be outside {region_key}"
        
        return True, None
    
    def add_manual_correction(self, location_name: str, latitude: float, longitude: float,
                            context: Optional[LocationContext] = None, notes: Optional[str] = None) -> bool:
        """
        Add a manual coordinate correction for a failed location.
        
        Args:
            location_name: Name of the location
            latitude: Manual latitude
            longitude: Manual longitude
            context: Optional context information
            notes: Optional notes about the correction
            
        Returns:
            True if correction was added successfully, False otherwise
        """
        # Validate coordinates
        is_valid, error_message = self.validate_coordinates(latitude, longitude, context)
        if not is_valid:
            logger.error(f"Invalid coordinates for {location_name}: {error_message}")
            return False
        
        # Create manual correction
        correction = ManualCoordinateInput(
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
            context=context,
            notes=notes
        )
        
        # Remove any existing correction for this location
        self.manual_corrections = [
            c for c in self.manual_corrections 
            if not (c.location_name == location_name and c.context == context)
        ]
        
        # Add new correction
        self.manual_corrections.append(correction)
        
        # Cache the result in the geocoding service
        self.geocoding_service.cache_result(
            location_name, 
            correction.to_coordinates(), 
            context
        )
        
        logger.info(f"Added manual correction for {location_name}: ({latitude}, {longitude})")
        return True
    
    def apply_bulk_corrections(self, corrections: List[Dict[str, Any]]) -> List[bool]:
        """
        Apply multiple manual corrections at once.
        
        Args:
            corrections: List of correction dictionaries with keys:
                        'location_name', 'latitude', 'longitude', 
                        optional 'context', 'notes'
                        
        Returns:
            List of boolean results indicating success for each correction
        """
        results = []
        
        for correction_data in corrections:
            try:
                location_name = correction_data['location_name']
                latitude = float(correction_data['latitude'])
                longitude = float(correction_data['longitude'])
                
                # Parse context if provided
                context = None
                if 'context' in correction_data and correction_data['context']:
                    context_data = correction_data['context']
                    context = LocationContext(
                        state=context_data.get('state'),
                        region=context_data.get('region'),
                        country=context_data.get('country')
                    )
                
                notes = correction_data.get('notes')
                
                success = self.add_manual_correction(
                    location_name, latitude, longitude, context, notes
                )
                results.append(success)
                
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Invalid correction data: {correction_data}, error: {e}")
                results.append(False)
        
        successful_count = sum(results)
        logger.info(f"Applied bulk corrections: {successful_count}/{len(corrections)} successful")
        
        return results
    
    def get_correction_suggestions(self, failed_location: FailedGeocoding) -> List[Dict[str, Any]]:
        """
        Generate suggestions for correcting a failed geocoding.
        
        Args:
            failed_location: Failed geocoding to generate suggestions for
            
        Returns:
            List of suggestion dictionaries
        """
        suggestions = []
        
        location_name = failed_location.location_name.lower()
        
        # Common location name variations
        variations = []
        
        # Remove common prefixes/suffixes
        if location_name.endswith(" city"):
            variations.append(location_name[:-5])
        if location_name.endswith(" town"):
            variations.append(location_name[:-5])
        if location_name.startswith("city of "):
            variations.append(location_name[8:])
        
        # Add state/region to search
        if failed_location.context:
            if failed_location.context.state:
                variations.append(f"{failed_location.location_name}, {failed_location.context.state}")
            if failed_location.context.region and failed_location.context.region != failed_location.context.state:
                variations.append(f"{failed_location.location_name}, {failed_location.context.region}")
        
        # Create suggestions
        for variation in variations:
            suggestions.append({
                "type": "retry_with_variation",
                "description": f"Try geocoding with variation: '{variation}'",
                "action": "retry",
                "query": variation
            })
        
        # Always suggest manual input
        suggestions.append({
            "type": "manual_input",
            "description": "Manually specify coordinates",
            "action": "manual",
            "instructions": "Look up coordinates using maps.google.com or similar service"
        })
        
        # Suggest skipping if not critical
        suggestions.append({
            "type": "skip",
            "description": "Skip this location (exclude from route)",
            "action": "skip",
            "warning": "Location will be excluded from the trip route"
        })
        
        return suggestions
    
    def export_corrections(self) -> Dict[str, Any]:
        """
        Export all manual corrections for backup or sharing.
        
        Returns:
            Dictionary containing all corrections
        """
        return {
            "corrections": [
                {
                    "location_name": c.location_name,
                    "latitude": c.latitude,
                    "longitude": c.longitude,
                    "context": {
                        "state": c.context.state if c.context else None,
                        "region": c.context.region if c.context else None,
                        "country": c.context.country if c.context else None
                    },
                    "notes": c.notes
                }
                for c in self.manual_corrections
            ],
            "export_timestamp": logger.info("Exported corrections"),
            "total_corrections": len(self.manual_corrections)
        }
    
    def import_corrections(self, corrections_data: Dict[str, Any]) -> int:
        """
        Import manual corrections from exported data.
        
        Args:
            corrections_data: Dictionary containing corrections to import
            
        Returns:
            Number of corrections successfully imported
        """
        if "corrections" not in corrections_data:
            logger.error("Invalid corrections data: missing 'corrections' key")
            return 0
        
        imported_count = 0
        
        for correction_data in corrections_data["corrections"]:
            try:
                location_name = correction_data["location_name"]
                latitude = correction_data["latitude"]
                longitude = correction_data["longitude"]
                
                context = None
                if correction_data.get("context"):
                    context_data = correction_data["context"]
                    context = LocationContext(
                        state=context_data.get("state"),
                        region=context_data.get("region"),
                        country=context_data.get("country")
                    )
                
                notes = correction_data.get("notes")
                
                if self.add_manual_correction(location_name, latitude, longitude, context, notes):
                    imported_count += 1
                    
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Failed to import correction: {correction_data}, error: {e}")
        
        logger.info(f"Imported {imported_count} corrections")
        return imported_count
    
    def get_manual_corrections(self) -> List[ManualCoordinateInput]:
        """
        Get all manual corrections.
        
        Returns:
            List of manual corrections
        """
        return self.manual_corrections.copy()
    
    def clear_manual_corrections(self) -> None:
        """Clear all manual corrections."""
        self.manual_corrections.clear()
        logger.info("Cleared all manual corrections")