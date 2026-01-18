"""
Example usage of the cache management system.

This module demonstrates how to use the hierarchical cache manager
and rate limiter for geographic data acquisition.
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from .integrated_manager import IntegratedCacheManager
from .models import BoundingBox, CacheLevel, RouteBufferConfig
from .rate_limiter import ServiceType


async def example_openstreetmap_acquirer(bounding_box: BoundingBox, 
                                       level: CacheLevel,
                                       params: dict) -> dict:
    """
    Example data acquirer function for OpenStreetMap data.
    
    In a real implementation, this would make actual API calls to
    OpenStreetMap's Overpass API or similar service.
    """
    # Simulate API call delay
    await asyncio.sleep(0.5)
    
    # Return mock geographic data
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [bounding_box.min_longitude, bounding_box.min_latitude],
                        [bounding_box.max_longitude, bounding_box.max_latitude]
                    ]
                },
                "properties": {
                    "highway": "primary",
                    "name": f"Example Road ({level.value})"
                }
            }
        ],
        "metadata": {
            "level": level.value,
            "bounds": bounding_box.to_dict(),
            "acquired_at": datetime.now().isoformat(),
            **params
        }
    }


async def example_usage():
    """Demonstrate cache management system usage."""
    print("Road Trip Animator Cache Management Example")
    print("=" * 50)
    
    # Initialize cache manager
    cache_dir = "example_cache"
    cache_manager = IntegratedCacheManager(
        cache_dir=cache_dir,
        max_cache_size_mb=100
    )
    
    # Register data acquirer
    cache_manager.register_data_acquirer(
        ServiceType.OPENSTREETMAP,
        example_openstreetmap_acquirer
    )
    
    # Create example route (Melbourne to Sydney)
    waypoints = [
        {
            "latitude": -37.8136,
            "longitude": 144.9631,
            "timestamp": "2024-01-01T09:00:00",
            "location_name": "Melbourne",
            "state": "Victoria",
            "region": "Melbourne"
        },
        {
            "latitude": -34.9285,
            "longitude": 138.6007,
            "timestamp": "2024-01-02T15:00:00",
            "location_name": "Adelaide",
            "state": "South Australia",
            "region": "Adelaide"
        },
        {
            "latitude": -33.8688,
            "longitude": 151.2093,
            "timestamp": "2024-01-04T18:00:00",
            "location_name": "Sydney",
            "state": "New South Wales",
            "region": "Sydney"
        }
    ]
    
    print(f"Example route: {len(waypoints)} waypoints from {waypoints[0]['location_name']} to {waypoints[-1]['location_name']}")
    
    # Configure route buffer
    buffer_config = RouteBufferConfig(
        buffer_distance_km=50.0,
        detail_levels={
            CacheLevel.COUNTRY: 100.0,
            CacheLevel.STATE: 75.0,
            CacheLevel.REGION: 50.0,
            CacheLevel.CITY: 25.0
        }
    )
    
    # Get cache coverage report
    print("\nCache Coverage Analysis:")
    print("-" * 30)
    coverage_report = cache_manager.get_cache_coverage_report(waypoints, buffer_config)
    print(f"Total required regions: {coverage_report['total_required_regions']}")
    print(f"Estimated download time: {coverage_report['estimated_download_time']:.1f} seconds")
    
    for level, stats in coverage_report['coverage_by_level'].items():
        print(f"  {level}: {stats['coverage_percentage']:.1f}% covered "
              f"({stats['missing_regions']} missing)")
    
    # Prepare route data with progress tracking
    print("\nPreparing Route Data:")
    print("-" * 30)
    
    def progress_callback(message: str, progress: float):
        print(f"  {message}: {progress * 100:.1f}%")
    
    preparation_results = await cache_manager.prepare_route_data(
        waypoints, buffer_config, progress_callback
    )
    
    print(f"\nData preparation complete!")
    print(f"Errors: {len(preparation_results['errors'])}")
    
    # Test individual data retrieval
    print("\nTesting Individual Data Retrieval:")
    print("-" * 30)
    
    # Define a test region around Melbourne
    melbourne_region = BoundingBox(
        min_latitude=-38.0,
        max_latitude=-37.5,
        min_longitude=144.5,
        max_longitude=145.5
    )
    
    # First request (cache miss)
    print("First request (should be cache miss):")
    start_time = datetime.now()
    data1 = await cache_manager.get_geographic_data(
        melbourne_region, CacheLevel.CITY
    )
    first_duration = (datetime.now() - start_time).total_seconds()
    print(f"  Retrieved {len(data1.get('features', []))} features in {first_duration:.3f}s")
    
    # Second request (cache hit)
    print("Second request (should be cache hit):")
    start_time = datetime.now()
    data2 = await cache_manager.get_geographic_data(
        melbourne_region, CacheLevel.CITY
    )
    second_duration = (datetime.now() - start_time).total_seconds()
    print(f"  Retrieved {len(data2.get('features', []))} features in {second_duration:.3f}s")
    print(f"  Speed improvement: {first_duration / second_duration:.1f}x faster")
    
    # Get comprehensive statistics
    print("\nCache and Rate Limiting Statistics:")
    print("-" * 30)
    stats = cache_manager.get_comprehensive_statistics()
    
    cache_stats = stats['cache_statistics']
    print(f"Cache entries: {cache_stats['total_entries']}")
    print(f"Cache size: {cache_stats['total_size_mb']:.1f} MB")
    print(f"Cache utilization: {cache_stats['utilization'] * 100:.1f}%")
    print(f"Cache hit rate: {cache_stats['hit_rate'] * 100:.1f}%")
    
    rate_stats = stats['rate_limiting_statistics']
    for service, service_stats in rate_stats.items():
        print(f"{service} requests: {service_stats['total_requests']} "
              f"(success rate: {service_stats['success_rate']:.1f}%)")
    
    # Cleanup and optimization
    print("\nPerforming Cache Cleanup:")
    print("-" * 30)
    cleanup_results = cache_manager.cleanup_and_optimize()
    print(f"Expired entries removed: {cleanup_results['expired_entries_removed']}")
    
    for recommendation in cleanup_results['recommendations']:
        print(f"  Recommendation: {recommendation}")
    
    print("\nExample completed successfully!")


def create_example_config():
    """Create an example rate limiting configuration file."""
    config = {
        "openstreetmap": {
            "requests_per_second": 1.0,
            "requests_per_minute": 60,
            "requests_per_hour": 3600,
            "burst_limit": 5,
            "backoff_multiplier": 2.0,
            "max_backoff_seconds": 300.0,
            "circuit_breaker_threshold": 5,
            "circuit_breaker_timeout": 60
        },
        "nominatim": {
            "requests_per_second": 0.5,
            "requests_per_minute": 30,
            "requests_per_hour": 1800,
            "burst_limit": 3,
            "backoff_multiplier": 2.0,
            "max_backoff_seconds": 600.0,
            "circuit_breaker_threshold": 3,
            "circuit_breaker_timeout": 120
        }
    }
    
    config_path = Path("example_rate_limits.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"Created example rate limiting configuration: {config_path}")
    return str(config_path)


if __name__ == "__main__":
    # Create example configuration
    config_file = create_example_config()
    
    # Run the example
    asyncio.run(example_usage())