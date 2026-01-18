"""
Geocoding service implementation with Nominatim integration.

This module provides the core geocoding functionality including:
- Context-aware geocoding using State/Region information
- Rate limiting and appropriate delays between requests
- Local caching of successful geocoding results
- Batch processing with partial failure handling
- User interaction for failed geocoding with manual coordinate input
"""

import time
import json
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from ..models import Coordinates


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class LocationContext:
    """Context information to improve geocoding accuracy."""
    state: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    
    def to_search_string(self) -> str:
        """Convert context to search string for geocoding."""
        parts = []
        if self.state:
            parts.append(self.state)
        if self.region and self.region != self.state:
            parts.append(self.region)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


@dataclass
class GeocodingResult:
    """Result of a geocoding operation."""
    location_name: str
    coordinates: Optional[Coordinates] = None
    success: bool = False
    error_message: Optional[str] = None
    confidence: float = 0.0
    display_name: Optional[str] = None
    context_used: Optional[LocationContext] = None
    
    def __post_init__(self):
        """Validate geocoding result."""
        if self.success and self.coordinates is None:
            raise ValueError("Successful geocoding result must have coordinates")
        if not self.success and self.error_message is None:
            raise ValueError("Failed geocoding result must have error message")


@dataclass
class FailedGeocoding:
    """Information about a failed geocoding attempt."""
    location_name: str
    context: Optional[LocationContext]
    error_message: str
    attempts: int = 1
    last_attempt: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "location_name": self.location_name,
            "context": {
                "state": self.context.state if self.context else None,
                "region": self.context.region if self.context else None,
                "country": self.context.country if self.context else None
            },
            "error_message": self.error_message,
            "attempts": self.attempts,
            "last_attempt": self.last_attempt.isoformat()
        }


class GeocodingService:
    """
    Geocoding service with Nominatim integration, caching, and error handling.
    
    Features:
    - Context-aware geocoding using State/Region information
    - Rate limiting with configurable delays
    - Local caching to avoid repeated API calls
    - Batch processing for efficiency
    - User agent: "road_trip_map_animator"
    """
    
    def __init__(self, 
                 cache_dir: Optional[Path] = None,
                 rate_limit_delay: float = 1.0,
                 max_retries: int = 3,
                 timeout: int = 10):
        """
        Initialize the geocoding service.
        
        Args:
            cache_dir: Directory for caching geocoding results
            rate_limit_delay: Minimum delay between API requests (seconds)
            max_retries: Maximum number of retry attempts for failed requests
            timeout: Request timeout in seconds
        """
        self.cache_dir = cache_dir or Path.home() / ".road_trip_animator" / "geocoding_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.timeout = timeout
        
        # Track last request time for rate limiting
        self._last_request_time = 0.0
        
        # Cache for this session
        self._session_cache: Dict[str, GeocodingResult] = {}
        
        # Failed geocoding tracking
        self._failed_locations: List[FailedGeocoding] = []
        
        # Nominatim base URL
        self.nominatim_url = "https://nominatim.openstreetmap.org/search"
        
        # User agent as specified in requirements
        self.user_agent = "road_trip_map_animator"
        
        logger.info(f"Initialized geocoding service with cache dir: {self.cache_dir}")
    
    def _get_cache_key(self, location: str, context: Optional[LocationContext] = None) -> str:
        """Generate cache key for location and context."""
        context_str = context.to_search_string() if context else ""
        combined = f"{location}|{context_str}".lower().strip()
        return hashlib.md5(combined.encode()).hexdigest()
    
    def _get_cache_file(self, cache_key: str) -> Path:
        """Get cache file path for a cache key."""
        return self.cache_dir / f"{cache_key}.json"
    
    def _load_from_cache(self, cache_key: str) -> Optional[GeocodingResult]:
        """Load geocoding result from cache."""
        cache_file = self._get_cache_file(cache_key)
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Reconstruct GeocodingResult
            coordinates = None
            if data.get('coordinates'):
                coordinates = Coordinates(
                    latitude=data['coordinates']['latitude'],
                    longitude=data['coordinates']['longitude']
                )
            
            context = None
            if data.get('context_used'):
                context = LocationContext(
                    state=data['context_used'].get('state'),
                    region=data['context_used'].get('region'),
                    country=data['context_used'].get('country')
                )
            
            result = GeocodingResult(
                location_name=data['location_name'],
                coordinates=coordinates,
                success=data['success'],
                error_message=data.get('error_message'),
                confidence=data.get('confidence', 0.0),
                display_name=data.get('display_name'),
                context_used=context
            )
            
            logger.debug(f"Loaded from cache: {data['location_name']}")
            return result
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to load cache file {cache_file}: {e}")
            # Remove corrupted cache file
            cache_file.unlink(missing_ok=True)
            return None
    
    def _save_to_cache(self, cache_key: str, result: GeocodingResult) -> None:
        """Save geocoding result to cache."""
        try:
            data = {
                "location_name": result.location_name,
                "success": result.success,
                "error_message": result.error_message,
                "confidence": result.confidence,
                "display_name": result.display_name,
                "cached_at": datetime.now().isoformat()
            }
            
            if result.coordinates:
                data["coordinates"] = {
                    "latitude": result.coordinates.latitude,
                    "longitude": result.coordinates.longitude
                }
            
            if result.context_used:
                data["context_used"] = {
                    "state": result.context_used.state,
                    "region": result.context_used.region,
                    "country": result.context_used.country
                }
            
            cache_file = self._get_cache_file(cache_key)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved to cache: {result.location_name}")
            
        except (OSError, json.JSONEncodeError) as e:
            logger.warning(f"Failed to save to cache: {e}")
    
    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between API requests."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    def _build_search_query(self, location: str, context: Optional[LocationContext] = None) -> str:
        """Build search query with context information."""
        query_parts = [location.strip()]
        
        if context:
            context_str = context.to_search_string()
            if context_str:
                query_parts.append(context_str)
        
        return ", ".join(query_parts)
    
    def _query_nominatim(self, query: str) -> Optional[Dict[str, Any]]:
        """Query Nominatim API for geocoding."""
        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1,
            'extratags': 1
        }
        
        url = f"{self.nominatim_url}?{urlencode(params)}"
        
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
            'Accept-Language': 'en'
        }
        
        for attempt in range(self.max_retries):
            try:
                self._enforce_rate_limit()
                
                request = Request(url, headers=headers)
                
                logger.debug(f"Querying Nominatim (attempt {attempt + 1}): {query}")
                
                with urlopen(request, timeout=self.timeout) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode('utf-8'))
                        if data:
                            return data[0]  # Return first result
                        else:
                            logger.debug(f"No results found for: {query}")
                            return None
                    else:
                        logger.warning(f"HTTP {response.status} from Nominatim for query: {query}")
                        
            except HTTPError as e:
                if e.code == 429:  # Too Many Requests
                    # Exponential backoff for rate limiting
                    backoff_time = self.rate_limit_delay * (2 ** attempt)
                    logger.warning(f"Rate limited by Nominatim, backing off for {backoff_time:.2f}s")
                    time.sleep(backoff_time)
                    continue
                else:
                    logger.error(f"HTTP error {e.code} from Nominatim: {e}")
                    
            except URLError as e:
                logger.error(f"URL error from Nominatim: {e}")
                
            except Exception as e:
                logger.error(f"Unexpected error querying Nominatim: {e}")
            
            # Wait before retry
            if attempt < self.max_retries - 1:
                time.sleep(self.rate_limit_delay * (attempt + 1))
        
        return None
    
    def geocode_location(self, location: str, context: Optional[LocationContext] = None) -> GeocodingResult:
        """
        Geocode a single location with optional context.
        
        Args:
            location: Location name to geocode
            context: Optional context information (state, region, country)
            
        Returns:
            GeocodingResult with coordinates if successful
        """
        if not location or not location.strip():
            return GeocodingResult(
                location_name=location,
                success=False,
                error_message="Empty location name"
            )
        
        location = location.strip()
        cache_key = self._get_cache_key(location, context)
        
        # Check session cache first
        if cache_key in self._session_cache:
            logger.debug(f"Found in session cache: {location}")
            return self._session_cache[cache_key]
        
        # Check persistent cache
        cached_result = self._load_from_cache(cache_key)
        if cached_result:
            self._session_cache[cache_key] = cached_result
            return cached_result
        
        # Build search query
        search_query = self._build_search_query(location, context)
        
        # Query Nominatim
        nominatim_result = self._query_nominatim(search_query)
        
        if nominatim_result:
            try:
                coordinates = Coordinates(
                    latitude=float(nominatim_result['lat']),
                    longitude=float(nominatim_result['lon'])
                )
                
                result = GeocodingResult(
                    location_name=location,
                    coordinates=coordinates,
                    success=True,
                    confidence=float(nominatim_result.get('importance', 0.0)),
                    display_name=nominatim_result.get('display_name'),
                    context_used=context
                )
                
                logger.info(f"Successfully geocoded: {location} -> {coordinates.latitude}, {coordinates.longitude}")
                
            except (ValueError, KeyError) as e:
                result = GeocodingResult(
                    location_name=location,
                    success=False,
                    error_message=f"Invalid response from geocoding service: {e}",
                    context_used=context
                )
                logger.error(f"Failed to parse Nominatim response for {location}: {e}")
        else:
            result = GeocodingResult(
                location_name=location,
                success=False,
                error_message="No results found from geocoding service",
                context_used=context
            )
            logger.warning(f"No geocoding results found for: {location}")
        
        # Cache the result
        self._session_cache[cache_key] = result
        self._save_to_cache(cache_key, result)
        
        # Track failed geocoding
        if not result.success:
            failed = FailedGeocoding(
                location_name=location,
                context=context,
                error_message=result.error_message or "Unknown error"
            )
            self._failed_locations.append(failed)
        
        return result
    
    def batch_geocode(self, locations: List[str], contexts: Optional[List[LocationContext]] = None) -> List[GeocodingResult]:
        """
        Geocode multiple locations with optional contexts.
        
        Args:
            locations: List of location names to geocode
            contexts: Optional list of context information (must match locations length)
            
        Returns:
            List of GeocodingResult objects
        """
        if not locations:
            return []
        
        if contexts and len(contexts) != len(locations):
            raise ValueError("Contexts list must match locations list length")
        
        results = []
        total = len(locations)
        
        logger.info(f"Starting batch geocoding of {total} locations")
        
        for i, location in enumerate(locations):
            context = contexts[i] if contexts else None
            
            logger.info(f"Geocoding {i + 1}/{total}: {location}")
            
            result = self.geocode_location(location, context)
            results.append(result)
            
            # Progress logging
            if (i + 1) % 10 == 0 or i + 1 == total:
                successful = sum(1 for r in results if r.success)
                logger.info(f"Progress: {i + 1}/{total} processed, {successful} successful")
        
        successful_count = sum(1 for r in results if r.success)
        failed_count = total - successful_count
        
        logger.info(f"Batch geocoding complete: {successful_count} successful, {failed_count} failed")
        
        return results
    
    def cache_result(self, location: str, coordinates: Coordinates, context: Optional[LocationContext] = None) -> None:
        """
        Manually cache a geocoding result (e.g., from user input).
        
        Args:
            location: Location name
            coordinates: Coordinates for the location
            context: Optional context information
        """
        result = GeocodingResult(
            location_name=location,
            coordinates=coordinates,
            success=True,
            confidence=1.0,  # Manual input has highest confidence
            display_name=f"{location} (manual)",
            context_used=context
        )
        
        cache_key = self._get_cache_key(location, context)
        self._session_cache[cache_key] = result
        self._save_to_cache(cache_key, result)
        
        # Remove from failed locations if it was there
        self._failed_locations = [
            f for f in self._failed_locations 
            if not (f.location_name == location and f.context == context)
        ]
        
        logger.info(f"Manually cached: {location} -> {coordinates.latitude}, {coordinates.longitude}")
    
    def get_failed_locations(self) -> List[FailedGeocoding]:
        """
        Get list of locations that failed geocoding.
        
        Returns:
            List of FailedGeocoding objects
        """
        return self._failed_locations.copy()
    
    def clear_failed_locations(self) -> None:
        """Clear the list of failed locations."""
        self._failed_locations.clear()
        logger.info("Cleared failed locations list")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        cache_files = list(self.cache_dir.glob("*.json"))
        
        return {
            "cache_directory": str(self.cache_dir),
            "cached_entries": len(cache_files),
            "session_cache_entries": len(self._session_cache),
            "failed_locations": len(self._failed_locations),
            "cache_size_mb": sum(f.stat().st_size for f in cache_files) / (1024 * 1024)
        }
    
    def clear_cache(self) -> None:
        """Clear all cached geocoding results."""
        # Clear session cache
        self._session_cache.clear()
        
        # Clear persistent cache
        cache_files = list(self.cache_dir.glob("*.json"))
        for cache_file in cache_files:
            cache_file.unlink(missing_ok=True)
        
        logger.info(f"Cleared {len(cache_files)} cache files")