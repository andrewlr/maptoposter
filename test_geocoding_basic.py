#!/usr/bin/env python3
"""
Basic test for the geocoding service functionality.

This test verifies that the geocoding service can be imported and basic
functionality works as expected.
"""

import sys
import tempfile
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from road_trip_animator.geocoding import (
    GeocodingService, 
    LocationContext, 
    InteractiveGeocodingCorrector,
    BatchGeocodingProcessor
)


def test_geocoding_service_initialization():
    """Test that the geocoding service can be initialized."""
    print("Testing geocoding service initialization...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir) / "geocoding_cache"
        
        service = GeocodingService(
            cache_dir=cache_dir,
            rate_limit_delay=0.1,  # Faster for testing
            max_retries=1,
            timeout=5
        )
        
        assert service.cache_dir == cache_dir
        assert service.rate_limit_delay == 0.1
        assert service.max_retries == 1
        assert service.timeout == 5
        assert service.user_agent == "road_trip_map_animator"
        
        print("✓ Geocoding service initialized successfully")


def test_location_context():
    """Test LocationContext functionality."""
    print("Testing LocationContext...")
    
    # Test empty context
    context = LocationContext()
    assert context.to_search_string() == ""
    
    # Test context with state
    context = LocationContext(state="California")
    assert context.to_search_string() == "California"
    
    # Test context with state and region
    context = LocationContext(state="California", region="Bay Area")
    assert context.to_search_string() == "California, Bay Area"
    
    # Test context with all fields
    context = LocationContext(state="California", region="Bay Area", country="United States")
    assert context.to_search_string() == "California, Bay Area, United States"
    
    # Test context with duplicate state/region
    context = LocationContext(state="California", region="California", country="United States")
    assert context.to_search_string() == "California, United States"
    
    print("✓ LocationContext working correctly")


def test_interactive_corrector():
    """Test InteractiveGeocodingCorrector initialization."""
    print("Testing InteractiveGeocodingCorrector...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir) / "geocoding_cache"
        
        service = GeocodingService(cache_dir=cache_dir, rate_limit_delay=0.1)
        corrector = InteractiveGeocodingCorrector(service)
        
        assert corrector.geocoding_service == service
        assert len(corrector.manual_corrections) == 0
        
        print("✓ InteractiveGeocodingCorrector initialized successfully")


def test_batch_processor():
    """Test BatchGeocodingProcessor initialization."""
    print("Testing BatchGeocodingProcessor...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir) / "geocoding_cache"
        progress_dir = Path(temp_dir) / "batch_progress"
        
        service = GeocodingService(cache_dir=cache_dir, rate_limit_delay=0.1)
        processor = BatchGeocodingProcessor(
            geocoding_service=service,
            progress_dir=progress_dir
        )
        
        assert processor.geocoding_service == service
        assert processor.progress_dir == progress_dir
        assert processor.interactive_corrector is not None
        
        print("✓ BatchGeocodingProcessor initialized successfully")


def test_cache_functionality():
    """Test basic cache functionality."""
    print("Testing cache functionality...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir) / "geocoding_cache"
        
        service = GeocodingService(cache_dir=cache_dir, rate_limit_delay=0.1)
        
        # Test cache key generation
        key1 = service._get_cache_key("San Francisco", None)
        key2 = service._get_cache_key("San Francisco", LocationContext(state="California"))
        key3 = service._get_cache_key("san francisco", None)
        
        # Same location, different context should have different keys
        assert key1 != key2
        
        # Case insensitive should have same key
        assert key1 == key3
        
        # Test cache stats
        stats = service.get_cache_stats()
        assert "cache_directory" in stats
        assert "cached_entries" in stats
        assert stats["cached_entries"] == 0
        
        print("✓ Cache functionality working correctly")


def main():
    """Run all basic tests."""
    print("Running basic geocoding service tests...\n")
    
    try:
        test_geocoding_service_initialization()
        test_location_context()
        test_interactive_corrector()
        test_batch_processor()
        test_cache_functionality()
        
        print("\n✅ All basic tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)