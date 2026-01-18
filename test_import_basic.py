#!/usr/bin/env python3
"""
Basic test to verify the data import functionality works.
"""

import tempfile
import json
from datetime import datetime
from pathlib import Path

from road_trip_animator.data import CSVItineraryParser, JSONRouteParser, UnifiedDataImporter


def test_csv_parser():
    """Test CSV itinerary parser with sample data."""
    print("Testing CSV parser...")
    
    # Create sample CSV data
    csv_content = """Month,Date,Day,Week,State,Region,Location,Booking Notes,Accommodation
January,15,Monday,Week 1,California,Bay Area,San Francisco,Flight arrival,Hotel Downtown
January,16,Tuesday,Week 1,California,Bay Area,San Jose,Conference,Conference Hotel
January,17,Wednesday,Week 1,California,Central Valley,Fresno,Road trip,Motel 6"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        temp_path = f.name
    
    try:
        parser = CSVItineraryParser()
        entries = parser.parse_file(temp_path)
        
        print(f"  Parsed {len(entries)} entries")
        for entry in entries:
            print(f"    {entry['timestamp']}: {entry['location_name']} ({entry.get('state', 'N/A')})")
        
        assert len(entries) == 3
        assert entries[0]['location_name'] == 'San Francisco'
        assert entries[0]['state'] == 'California'
        print("  ✓ CSV parser test passed")
        
    finally:
        Path(temp_path).unlink()


def test_json_parser():
    """Test JSON route parser with sample data."""
    print("Testing JSON parser...")
    
    # Create sample JSON data
    json_data = {
        "waypoints": [
            {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "timestamp": "2024-01-15T10:00:00",
                "location_name": "San Francisco",
                "state": "California",
                "region": "Bay Area"
            },
            {
                "latitude": 37.3382,
                "longitude": -121.8863,
                "timestamp": "2024-01-16T14:00:00",
                "location_name": "San Jose",
                "state": "California",
                "region": "Bay Area"
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(json_data, f)
        temp_path = f.name
    
    try:
        parser = JSONRouteParser()
        waypoints, route_overrides = parser.parse_file(temp_path)
        
        print(f"  Parsed {len(waypoints)} waypoints")
        for wp in waypoints:
            print(f"    {wp.timestamp}: {wp.location_name} ({wp.latitude}, {wp.longitude})")
        
        assert len(waypoints) == 2
        assert waypoints[0].location_name == 'San Francisco'
        assert waypoints[0].latitude == 37.7749
        print("  ✓ JSON parser test passed")
        
    finally:
        Path(temp_path).unlink()


def test_unified_importer():
    """Test unified data importer."""
    print("Testing unified importer...")
    
    # Test with JSON file
    json_data = {
        "waypoints": [
            {
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timestamp": "2024-01-01T12:00:00",
                "location_name": "New York City"
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(json_data, f)
        temp_path = f.name
    
    try:
        importer = UnifiedDataImporter()
        waypoints, route_overrides = importer.import_file(temp_path)
        
        print(f"  Imported {len(waypoints)} waypoints via unified importer")
        assert len(waypoints) == 1
        assert waypoints[0].location_name == 'New York City'
        print("  ✓ Unified importer test passed")
        
    finally:
        Path(temp_path).unlink()


if __name__ == '__main__':
    print("Running basic import functionality tests...\n")
    
    try:
        test_csv_parser()
        print()
        test_json_parser()
        print()
        test_unified_importer()
        print("\n✓ All tests passed!")
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        raise