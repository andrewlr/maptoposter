"""
Cache data models for hierarchical geographic data storage.

This module defines the data structures used for organizing and managing
cached geographic data in a hierarchical manner.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Dict, Tuple, Any, Set
import json
import hashlib
from pathlib import Path


class CacheLevel(Enum):
    """Hierarchical cache levels for geographic data organization."""
    COUNTRY = "country"
    STATE = "state"
    REGION = "region"
    CITY = "city"


@dataclass
class BoundingBox:
    """Geographic bounding box for spatial indexing."""
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float
    
    def __post_init__(self):
        """Validate bounding box coordinates."""
        if self.min_latitude >= self.max_latitude:
            raise ValueError("Minimum latitude must be less than maximum latitude")
        if self.min_longitude >= self.max_longitude:
            raise ValueError("Minimum longitude must be less than maximum longitude")
        if not -90 <= self.min_latitude <= 90:
            raise ValueError(f"Minimum latitude must be between -90 and 90, got {self.min_latitude}")
        if not -90 <= self.max_latitude <= 90:
            raise ValueError(f"Maximum latitude must be between -90 and 90, got {self.max_latitude}")
        if not -180 <= self.min_longitude <= 180:
            raise ValueError(f"Minimum longitude must be between -180 and 180, got {self.min_longitude}")
        if not -180 <= self.max_longitude <= 180:
            raise ValueError(f"Maximum longitude must be between -180 and 180, got {self.max_longitude}")
    
    def contains(self, other: 'BoundingBox') -> bool:
        """Check if this bounding box completely contains another."""
        return (self.min_latitude <= other.min_latitude and
                self.max_latitude >= other.max_latitude and
                self.min_longitude <= other.min_longitude and
                self.max_longitude >= other.max_longitude)
    
    def intersects(self, other: 'BoundingBox') -> bool:
        """Check if this bounding box intersects with another."""
        return not (self.max_latitude < other.min_latitude or
                   self.min_latitude > other.max_latitude or
                   self.max_longitude < other.min_longitude or
                   self.min_longitude > other.max_longitude)
    
    def area(self) -> float:
        """Calculate the area of the bounding box in square degrees."""
        return (self.max_latitude - self.min_latitude) * (self.max_longitude - self.min_longitude)
    
    def center(self) -> Tuple[float, float]:
        """Get the center point of the bounding box."""
        center_lat = (self.min_latitude + self.max_latitude) / 2
        center_lon = (self.min_longitude + self.max_longitude) / 2
        return (center_lat, center_lon)
    
    def expand_by_buffer(self, buffer_km: float) -> 'BoundingBox':
        """Expand bounding box by a buffer distance in kilometers."""
        # Approximate conversion: 1 degree ≈ 111 km
        buffer_degrees = buffer_km / 111.0
        
        return BoundingBox(
            min_latitude=max(-90, self.min_latitude - buffer_degrees),
            max_latitude=min(90, self.max_latitude + buffer_degrees),
            min_longitude=max(-180, self.min_longitude - buffer_degrees),
            max_longitude=min(180, self.max_longitude + buffer_degrees)
        )
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for JSON serialization."""
        return {
            "min_latitude": self.min_latitude,
            "max_latitude": self.max_latitude,
            "min_longitude": self.min_longitude,
            "max_longitude": self.max_longitude
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> 'BoundingBox':
        """Create from dictionary."""
        return cls(
            min_latitude=data["min_latitude"],
            max_latitude=data["max_latitude"],
            min_longitude=data["min_longitude"],
            max_longitude=data["max_longitude"]
        )


@dataclass
class GeographicDataEntry:
    """A single entry in the geographic data cache."""
    cache_key: str
    bounding_box: BoundingBox
    cache_level: CacheLevel
    data_path: str
    created_at: datetime
    last_accessed: datetime
    access_count: int
    data_size_bytes: int
    compression_ratio: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate geographic data entry."""
        if not self.cache_key or not self.cache_key.strip():
            raise ValueError("Cache key cannot be empty")
        if not self.data_path or not self.data_path.strip():
            raise ValueError("Data path cannot be empty")
        if self.access_count < 0:
            raise ValueError("Access count cannot be negative")
        if self.data_size_bytes < 0:
            raise ValueError("Data size cannot be negative")
        if self.compression_ratio <= 0:
            raise ValueError("Compression ratio must be positive")
    
    def update_access(self) -> None:
        """Update access statistics."""
        self.last_accessed = datetime.now()
        self.access_count += 1
    
    def is_expired(self, max_age: timedelta) -> bool:
        """Check if the cache entry has expired."""
        return datetime.now() - self.created_at > max_age
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "cache_key": self.cache_key,
            "bounding_box": self.bounding_box.to_dict(),
            "cache_level": self.cache_level.value,
            "data_path": self.data_path,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "data_size_bytes": self.data_size_bytes,
            "compression_ratio": self.compression_ratio,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GeographicDataEntry':
        """Create from dictionary."""
        return cls(
            cache_key=data["cache_key"],
            bounding_box=BoundingBox.from_dict(data["bounding_box"]),
            cache_level=CacheLevel(data["cache_level"]),
            data_path=data["data_path"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            access_count=data["access_count"],
            data_size_bytes=data["data_size_bytes"],
            compression_ratio=data.get("compression_ratio", 1.0),
            metadata=data.get("metadata", {})
        )


@dataclass
class CacheIndex:
    """Spatial index for efficient cache lookups."""
    entries: Dict[str, GeographicDataEntry] = field(default_factory=dict)
    level_index: Dict[CacheLevel, Set[str]] = field(default_factory=dict)
    spatial_index: Dict[Tuple[int, int], Set[str]] = field(default_factory=dict)
    total_size_bytes: int = 0
    
    def __post_init__(self):
        """Initialize level index if empty."""
        if not self.level_index:
            for level in CacheLevel:
                self.level_index[level] = set()
    
    def add_entry(self, entry: GeographicDataEntry) -> None:
        """Add an entry to the index."""
        self.entries[entry.cache_key] = entry
        self.level_index[entry.cache_level].add(entry.cache_key)
        self.total_size_bytes += entry.data_size_bytes
        
        # Add to spatial index (simple grid-based indexing)
        grid_cells = self._get_grid_cells(entry.bounding_box)
        for cell in grid_cells:
            if cell not in self.spatial_index:
                self.spatial_index[cell] = set()
            self.spatial_index[cell].add(entry.cache_key)
    
    def remove_entry(self, cache_key: str) -> Optional[GeographicDataEntry]:
        """Remove an entry from the index."""
        if cache_key not in self.entries:
            return None
        
        entry = self.entries.pop(cache_key)
        self.level_index[entry.cache_level].discard(cache_key)
        self.total_size_bytes -= entry.data_size_bytes
        
        # Remove from spatial index
        grid_cells = self._get_grid_cells(entry.bounding_box)
        for cell in grid_cells:
            if cell in self.spatial_index:
                self.spatial_index[cell].discard(cache_key)
                if not self.spatial_index[cell]:
                    del self.spatial_index[cell]
        
        return entry
    
    def find_containing_entries(self, bounding_box: BoundingBox, 
                              level: Optional[CacheLevel] = None) -> List[GeographicDataEntry]:
        """Find entries that contain the given bounding box."""
        candidates = self._get_spatial_candidates(bounding_box)
        
        if level:
            candidates = candidates.intersection(self.level_index[level])
        
        containing_entries = []
        for cache_key in candidates:
            entry = self.entries[cache_key]
            if entry.bounding_box.contains(bounding_box):
                containing_entries.append(entry)
        
        return containing_entries
    
    def find_intersecting_entries(self, bounding_box: BoundingBox,
                                level: Optional[CacheLevel] = None) -> List[GeographicDataEntry]:
        """Find entries that intersect with the given bounding box."""
        candidates = self._get_spatial_candidates(bounding_box)
        
        if level:
            candidates = candidates.intersection(self.level_index[level])
        
        intersecting_entries = []
        for cache_key in candidates:
            entry = self.entries[cache_key]
            if entry.bounding_box.intersects(bounding_box):
                intersecting_entries.append(entry)
        
        return intersecting_entries
    
    def get_entries_by_level(self, level: CacheLevel) -> List[GeographicDataEntry]:
        """Get all entries at a specific cache level."""
        return [self.entries[key] for key in self.level_index[level]]
    
    def get_lru_entries(self, count: int) -> List[GeographicDataEntry]:
        """Get the least recently used entries."""
        all_entries = list(self.entries.values())
        all_entries.sort(key=lambda e: e.last_accessed)
        return all_entries[:count]
    
    def _get_grid_cells(self, bounding_box: BoundingBox) -> Set[Tuple[int, int]]:
        """Get grid cells that intersect with the bounding box."""
        # Simple grid: 1-degree cells
        min_x = int(bounding_box.min_longitude)
        max_x = int(bounding_box.max_longitude)
        min_y = int(bounding_box.min_latitude)
        max_y = int(bounding_box.max_latitude)
        
        cells = set()
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                cells.add((x, y))
        
        return cells
    
    def _get_spatial_candidates(self, bounding_box: BoundingBox) -> Set[str]:
        """Get candidate cache keys from spatial index."""
        grid_cells = self._get_grid_cells(bounding_box)
        candidates = set()
        
        for cell in grid_cells:
            if cell in self.spatial_index:
                candidates.update(self.spatial_index[cell])
        
        return candidates
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
            "level_index": {level.value: list(keys) for level, keys in self.level_index.items()},
            "total_size_bytes": self.total_size_bytes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheIndex':
        """Create from dictionary."""
        index = cls()
        
        # Restore entries
        for key, entry_data in data["entries"].items():
            entry = GeographicDataEntry.from_dict(entry_data)
            index.add_entry(entry)
        
        index.total_size_bytes = data["total_size_bytes"]
        return index


@dataclass
class RouteBufferConfig:
    """Configuration for route-focused data acquisition."""
    buffer_distance_km: float
    detail_levels: Dict[CacheLevel, float] = field(default_factory=dict)
    priority_areas: List[BoundingBox] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate route buffer configuration."""
        if self.buffer_distance_km <= 0:
            raise ValueError("Buffer distance must be positive")
        
        # Set default detail levels if not provided
        if not self.detail_levels:
            self.detail_levels = {
                CacheLevel.COUNTRY: 50.0,  # 50km buffer for country-level data
                CacheLevel.STATE: 25.0,    # 25km buffer for state-level data
                CacheLevel.REGION: 10.0,   # 10km buffer for region-level data
                CacheLevel.CITY: 5.0       # 5km buffer for city-level data
            }
    
    def get_buffer_for_level(self, level: CacheLevel) -> float:
        """Get buffer distance for a specific cache level."""
        return self.detail_levels.get(level, self.buffer_distance_km)


def generate_cache_key(bounding_box: BoundingBox, level: CacheLevel, 
                      additional_params: Optional[Dict[str, Any]] = None) -> str:
    """Generate a unique cache key for geographic data."""
    # Create a string representation of the key components
    key_components = [
        f"level:{level.value}",
        f"bounds:{bounding_box.min_latitude:.6f},{bounding_box.min_longitude:.6f}",
        f"to:{bounding_box.max_latitude:.6f},{bounding_box.max_longitude:.6f}"
    ]
    
    if additional_params:
        # Sort parameters for consistent key generation
        sorted_params = sorted(additional_params.items())
        for key, value in sorted_params:
            key_components.append(f"{key}:{value}")
    
    key_string = "|".join(key_components)
    
    # Generate SHA-256 hash for consistent, collision-resistant keys
    return hashlib.sha256(key_string.encode('utf-8')).hexdigest()[:16]