#!/usr/bin/env python3
"""
Example usage of the Road Trip Animator geocoding service.

This script demonstrates how to use the geocoding service with caching,
batch processing, and interactive correction capabilities.
"""

import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

from road_trip_animator.geocoding import (
    GeocodingService,
    LocationContext,
    InteractiveGeocodingCorrector,
    BatchGeocodingProcessor,
    BatchProcessingConfig
)


def example_basic_geocoding():
    """Example of basic geocoding functionality."""
    print("=== Basic Geocoding Example ===")
    
    # Initialize the geocoding service
    service = GeocodingService(rate_limit_delay=1.0)  # 1 second delay between requests
    
    # Geocode a single location
    result = service.geocode_location("San Francisco")
    
    if result.success:
        print(f"✓ {result.location_name}: {result.coordinates.latitude}, {result.coordinates.longitude}")
        print(f"  Display name: {result.display_name}")
        print(f"  Confidence: {result.confidence:.2f}")
    else:
        print(f"✗ Failed to geocode {result.location_name}: {result.error_message}")
    
    # Geocode with context
    context = LocationContext(state="California", country="United States")
    result = service.geocode_location("Berkeley", context)
    
    if result.success:
        print(f"✓ {result.location_name} (with context): {result.coordinates.latitude}, {result.coordinates.longitude}")
    else:
        print(f"✗ Failed to geocode {result.location_name}: {result.error_message}")
    
    print()


def example_batch_geocoding():
    """Example of batch geocoding with progress tracking."""
    print("=== Batch Geocoding Example ===")
    
    # Initialize services
    service = GeocodingService(rate_limit_delay=0.5)  # Faster for demo
    processor = BatchGeocodingProcessor(service)
    
    # Sample locations
    locations = [
        "San Francisco",
        "Los Angeles", 
        "Seattle",
        "Portland",
        "Denver"
    ]
    
    # Corresponding contexts
    contexts = [
        LocationContext(state="California"),
        LocationContext(state="California"),
        LocationContext(state="Washington"),
        LocationContext(state="Oregon"),
        LocationContext(state="Colorado")
    ]
    
    # Configure batch processing
    config = BatchProcessingConfig(
        batch_size=10,
        save_progress_every=2,
        max_retries=2
    )
    
    print(f"Processing {len(locations)} locations...")
    
    # Process batch
    state = processor.process_batch(
        locations=locations,
        contexts=contexts,
        config=config,
        session_id="demo_batch"
    )
    
    print(f"Batch complete: {state.successful_count}/{state.total_locations} successful")
    
    # Show results
    for result in state.results:
        if result.success:
            print(f"✓ {result.location_name}: {result.coordinates.latitude:.4f}, {result.coordinates.longitude:.4f}")
        else:
            print(f"✗ {result.location_name}: {result.error_message}")
    
    print()


def example_interactive_correction():
    """Example of interactive correction for failed geocoding."""
    print("=== Interactive Correction Example ===")
    
    # Initialize services
    service = GeocodingService(rate_limit_delay=0.1)
    corrector = InteractiveGeocodingCorrector(service)
    
    # Try to geocode a location that might fail
    result = service.geocode_location("Nonexistent City")
    
    if not result.success:
        print(f"Geocoding failed for: {result.location_name}")
        print(f"Error: {result.error_message}")
        
        # Add manual correction
        print("Adding manual correction...")
        success = corrector.add_manual_correction(
            location_name="Nonexistent City",
            latitude=37.7749,  # San Francisco coordinates as example
            longitude=-122.4194,
            notes="Manual correction for demo"
        )
        
        if success:
            print("✓ Manual correction added successfully")
            
            # Try geocoding again (should use cached manual result)
            corrected_result = service.geocode_location("Nonexistent City")
            if corrected_result.success:
                print(f"✓ Now geocodes to: {corrected_result.coordinates.latitude}, {corrected_result.coordinates.longitude}")
        else:
            print("✗ Failed to add manual correction")
    
    print()


def example_cache_management():
    """Example of cache management functionality."""
    print("=== Cache Management Example ===")
    
    service = GeocodingService(rate_limit_delay=0.1)
    
    # Get initial cache stats
    stats = service.get_cache_stats()
    print(f"Initial cache stats:")
    print(f"  Cached entries: {stats['cached_entries']}")
    print(f"  Session cache: {stats['session_cache_entries']}")
    print(f"  Cache size: {stats['cache_size_mb']:.2f} MB")
    
    # Geocode some locations to populate cache
    locations = ["New York", "Chicago", "Miami"]
    for location in locations:
        result = service.geocode_location(location)
        if result.success:
            print(f"✓ Cached: {location}")
    
    # Get updated cache stats
    stats = service.get_cache_stats()
    print(f"\nUpdated cache stats:")
    print(f"  Cached entries: {stats['cached_entries']}")
    print(f"  Session cache: {stats['session_cache_entries']}")
    print(f"  Cache size: {stats['cache_size_mb']:.2f} MB")
    
    print()


def main():
    """Run all examples."""
    print("Road Trip Animator Geocoding Service Examples")
    print("=" * 50)
    print()
    
    try:
        example_basic_geocoding()
        example_batch_geocoding()
        example_interactive_correction()
        example_cache_management()
        
        print("✅ All examples completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️  Examples interrupted by user")
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()