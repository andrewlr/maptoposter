"""
Hierarchical cache manager for geographic data.

This module implements the core cache management functionality including
hierarchical data organization, spatial indexing, and route-focused data acquisition.
"""

import json
import gzip
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Set, Tuple
import logging

from .models import (
    BoundingBox, GeographicDataEntry, CacheIndex, CacheLevel, 
    RouteBufferConfig, generate_cache_key
)


logger = logging.getLogger(__name__)


class CacheManager:
    """
    Hierarchical cache manager for geographic data with spatial indexing
    and route-focused data acquisition.
    """
    
    def __init__(self, cache_dir: str, max_cache_size_mb: int = 1000,
                 max_age_days: int = 30, compression_enabled: bool = True):
        """
        Initialize the cache manager.
        
        Args:
            cache_dir: Directory for cache storage
            max_cache_size_mb: Maximum cache size in megabytes
            max_age_days: Maximum age for cache entries in days
            compression_enabled: Whether to compress cached data
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_cache_size_bytes = max_cache_size_mb * 1024 * 1024
        self.max_age = timedelta(days=max_age_days)
        self.compression_enabled = compression_enabled
        
        # Initialize cache index
        self.index = self._load_index()
        
        # Statistics tracking
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "data_downloaded": 0,
            "data_evicted": 0,
            "compression_savings": 0
        }
        
        logger.info(f"Cache manager initialized with {len(self.index.entries)} entries, "
                   f"total size: {self.index.total_size_bytes / 1024 / 1024:.1f} MB")
    
    def get_cached_data(self, bounding_box: BoundingBox, level: CacheLevel,
                       additional_params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached geographic data for the specified region.
        
        Args:
            bounding_box: Geographic region to retrieve
            level: Cache level for the data
            additional_params: Additional parameters for cache key generation
            
        Returns:
            Cached data if available, None otherwise
        """
        # First try exact match
        cache_key = generate_cache_key(bounding_box, level, additional_params)
        
        if cache_key in self.index.entries:
            entry = self.index.entries[cache_key]
            entry.update_access()
            self.stats["cache_hits"] += 1
            
            try:
                data = self._load_data_file(entry.data_path)
                logger.debug(f"Cache hit for key {cache_key}")
                return data
            except Exception as e:
                logger.warning(f"Failed to load cached data for key {cache_key}: {e}")
                # Remove corrupted entry
                self._remove_entry(cache_key)
        
        # Try to find containing entries at higher levels
        containing_entries = self.index.find_containing_entries(bounding_box, level)
        
        if containing_entries:
            # Use the smallest containing entry (most specific)
            best_entry = min(containing_entries, key=lambda e: e.bounding_box.area())
            best_entry.update_access()
            self.stats["cache_hits"] += 1
            
            try:
                data = self._load_data_file(best_entry.data_path)
                # Extract subset for the requested bounding box
                subset_data = self._extract_subset(data, bounding_box)
                logger.debug(f"Cache hit with subset extraction from key {best_entry.cache_key}")
                return subset_data
            except Exception as e:
                logger.warning(f"Failed to load cached data for key {best_entry.cache_key}: {e}")
                self._remove_entry(best_entry.cache_key)
        
        self.stats["cache_misses"] += 1
        logger.debug(f"Cache miss for region {bounding_box.to_dict()}")
        return None
    
    def store_data(self, bounding_box: BoundingBox, level: CacheLevel, data: Dict[str, Any],
                  additional_params: Optional[Dict[str, Any]] = None) -> str:
        """
        Store geographic data in the cache.
        
        Args:
            bounding_box: Geographic region of the data
            level: Cache level for the data
            data: Geographic data to store
            additional_params: Additional parameters for cache key generation
            
        Returns:
            Cache key for the stored data
        """
        cache_key = generate_cache_key(bounding_box, level, additional_params)
        
        # Check if we need to make space
        self._ensure_cache_space()
        
        # Store the data file
        data_path = self._get_data_file_path(cache_key)
        original_size = self._save_data_file(data, data_path)
        
        # Calculate compression ratio
        compressed_size = data_path.stat().st_size
        compression_ratio = original_size / compressed_size if compressed_size > 0 else 1.0
        
        # Create cache entry
        entry = GeographicDataEntry(
            cache_key=cache_key,
            bounding_box=bounding_box,
            cache_level=level,
            data_path=str(data_path),
            created_at=datetime.now(),
            last_accessed=datetime.now(),
            access_count=1,
            data_size_bytes=compressed_size,
            compression_ratio=compression_ratio,
            metadata=additional_params or {}
        )
        
        # Add to index
        self.index.add_entry(entry)
        self._save_index()
        
        # Update statistics
        self.stats["compression_savings"] += original_size - compressed_size
        
        logger.info(f"Stored data for key {cache_key}, size: {compressed_size / 1024:.1f} KB, "
                   f"compression: {compression_ratio:.2f}x")
        
        return cache_key
    
    def calculate_route_buffer(self, waypoints: list, config: RouteBufferConfig) -> BoundingBox:
        """
        Calculate the minimum bounding box covering a route with buffer.
        
        Args:
            waypoints: List of waypoint dictionaries with 'latitude' and 'longitude' keys
            config: Buffer configuration
            
        Returns:
            Bounding box covering the route with buffer
        """
        if not waypoints:
            raise ValueError("Route must have at least one waypoint")
        
        # Find route bounds
        latitudes = [wp['latitude'] if isinstance(wp, dict) else wp.latitude for wp in waypoints]
        longitudes = [wp['longitude'] if isinstance(wp, dict) else wp.longitude for wp in waypoints]
        
        route_bounds = BoundingBox(
            min_latitude=min(latitudes),
            max_latitude=max(latitudes),
            min_longitude=min(longitudes),
            max_longitude=max(longitudes)
        )
        
        # Expand by buffer distance
        buffered_bounds = route_bounds.expand_by_buffer(config.buffer_distance_km)
        
        logger.info(f"Route buffer calculated: {buffered_bounds.to_dict()}, "
                   f"buffer: {config.buffer_distance_km} km")
        
        return buffered_bounds
    
    def get_required_data_regions(self, waypoints: list, config: RouteBufferConfig) -> Dict[CacheLevel, List[BoundingBox]]:
        """
        Determine what geographic data regions are needed for a route.
        
        Args:
            waypoints: List of waypoint dictionaries with 'latitude' and 'longitude' keys
            config: Buffer configuration
            
        Returns:
            Dictionary mapping cache levels to required bounding boxes
        """
        required_regions = {}
        
        # Calculate overall route buffer
        route_buffer = self.calculate_route_buffer(waypoints, config)
        
        for level in CacheLevel:
            level_buffer = config.get_buffer_for_level(level)
            level_bounds = route_buffer.expand_by_buffer(level_buffer - config.buffer_distance_km)
            
            # Check what data we already have
            existing_entries = self.index.find_containing_entries(level_bounds, level)
            
            if not existing_entries:
                # Need to download data for this level
                required_regions[level] = [level_bounds]
            else:
                # Check for gaps in coverage
                gaps = self._find_coverage_gaps(level_bounds, existing_entries)
                if gaps:
                    required_regions[level] = gaps
        
        return required_regions
    
    def cleanup_expired_entries(self) -> int:
        """
        Remove expired cache entries.
        
        Returns:
            Number of entries removed
        """
        expired_keys = []
        
        for key, entry in self.index.entries.items():
            if entry.is_expired(self.max_age):
                expired_keys.append(key)
        
        removed_count = 0
        for key in expired_keys:
            if self._remove_entry(key):
                removed_count += 1
        
        if removed_count > 0:
            self._save_index()
            logger.info(f"Cleaned up {removed_count} expired cache entries")
        
        return removed_count
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get cache usage statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        total_entries = len(self.index.entries)
        total_size_mb = self.index.total_size_bytes / 1024 / 1024
        
        level_stats = {}
        for level in CacheLevel:
            entries = self.index.get_entries_by_level(level)
            level_stats[level.value] = {
                "count": len(entries),
                "size_mb": sum(e.data_size_bytes for e in entries) / 1024 / 1024
            }
        
        hit_rate = (self.stats["cache_hits"] / 
                   (self.stats["cache_hits"] + self.stats["cache_misses"]) 
                   if (self.stats["cache_hits"] + self.stats["cache_misses"]) > 0 else 0)
        
        return {
            "total_entries": total_entries,
            "total_size_mb": total_size_mb,
            "max_size_mb": self.max_cache_size_bytes / 1024 / 1024,
            "utilization": total_size_mb / (self.max_cache_size_bytes / 1024 / 1024),
            "hit_rate": hit_rate,
            "level_statistics": level_stats,
            "compression_savings_mb": self.stats["compression_savings"] / 1024 / 1024,
            **self.stats
        }
    
    def _load_index(self) -> CacheIndex:
        """Load cache index from disk."""
        index_path = self.cache_dir / "index.json"
        
        if index_path.exists():
            try:
                with open(index_path, 'r') as f:
                    data = json.load(f)
                return CacheIndex.from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load cache index: {e}")
        
        return CacheIndex()
    
    def _save_index(self) -> None:
        """Save cache index to disk."""
        index_path = self.cache_dir / "index.json"
        
        try:
            with open(index_path, 'w') as f:
                json.dump(self.index.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")
    
    def _get_data_file_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        filename = f"{cache_key}.json"
        if self.compression_enabled:
            filename += ".gz"
        return self.cache_dir / "data" / filename
    
    def _save_data_file(self, data: Dict[str, Any], file_path: Path) -> int:
        """
        Save data to file with optional compression.
        
        Returns:
            Original uncompressed size in bytes
        """
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Serialize to JSON
        json_data = json.dumps(data, separators=(',', ':')).encode('utf-8')
        original_size = len(json_data)
        
        if self.compression_enabled:
            with gzip.open(file_path, 'wb') as f:
                f.write(json_data)
        else:
            with open(file_path, 'wb') as f:
                f.write(json_data)
        
        return original_size
    
    def _load_data_file(self, file_path: str) -> Dict[str, Any]:
        """Load data from file with optional decompression."""
        path = Path(file_path)
        
        if path.suffix == '.gz':
            with gzip.open(path, 'rt') as f:
                return json.load(f)
        else:
            with open(path, 'r') as f:
                return json.load(f)
    
    def _extract_subset(self, data: Dict[str, Any], bounding_box: BoundingBox) -> Dict[str, Any]:
        """
        Extract a subset of geographic data for a specific bounding box.
        
        This is a simplified implementation - in practice, this would need
        to filter geographic features based on the bounding box.
        """
        # For now, return the full dataset
        # TODO: Implement proper geographic filtering
        return data
    
    def _ensure_cache_space(self) -> None:
        """Ensure there's enough space in the cache for new data."""
        while self.index.total_size_bytes > self.max_cache_size_bytes * 0.9:
            # Remove LRU entries until we're under 90% capacity
            lru_entries = self.index.get_lru_entries(10)
            
            if not lru_entries:
                break
            
            for entry in lru_entries:
                self._remove_entry(entry.cache_key)
                self.stats["data_evicted"] += entry.data_size_bytes
                
                if self.index.total_size_bytes <= self.max_cache_size_bytes * 0.8:
                    break
    
    def _remove_entry(self, cache_key: str) -> bool:
        """Remove a cache entry and its data file."""
        entry = self.index.remove_entry(cache_key)
        
        if entry:
            # Remove data file
            try:
                Path(entry.data_path).unlink(missing_ok=True)
                logger.debug(f"Removed cache entry {cache_key}")
                return True
            except Exception as e:
                logger.warning(f"Failed to remove data file for key {cache_key}: {e}")
        
        return False
    
    def _find_coverage_gaps(self, target_bounds: BoundingBox, 
                          existing_entries: List[GeographicDataEntry]) -> List[BoundingBox]:
        """
        Find gaps in geographic data coverage.
        
        This is a simplified implementation that assumes no gaps if any
        containing entry exists. A more sophisticated implementation would
        perform actual geometric coverage analysis.
        """
        # Check if target bounds are fully covered
        for entry in existing_entries:
            if entry.bounding_box.contains(target_bounds):
                return []  # Fully covered, no gaps
        
        # For now, return the target bounds as a gap
        # TODO: Implement proper gap analysis
        return [target_bounds]