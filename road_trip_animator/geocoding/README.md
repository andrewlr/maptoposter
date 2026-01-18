# Geocoding Service

The geocoding service provides functionality to convert location names to coordinates using external services like Nominatim, with caching and error handling capabilities.

## Features

- **Context-aware geocoding**: Uses State/Region information to improve accuracy
- **Rate limiting**: Respects API limits with configurable delays
- **Local caching**: Avoids repeated API calls for the same locations
- **Batch processing**: Efficiently processes large lists of locations
- **Interactive correction**: Manual coordinate input for failed geocoding
- **Progress tracking**: Save and resume batch operations
- **Error handling**: Comprehensive error reporting and recovery

## Quick Start

```python
from road_trip_animator.geocoding import GeocodingService, LocationContext

# Initialize the service
service = GeocodingService()

# Geocode a single location
result = service.geocode_location("San Francisco")
if result.success:
    print(f"Coordinates: {result.coordinates.latitude}, {result.coordinates.longitude}")

# Geocode with context for better accuracy
context = LocationContext(state="California", country="United States")
result = service.geocode_location("Berkeley", context)
```

## Components

### GeocodingService

The main service class that handles geocoding operations.

**Key Features:**
- Nominatim integration with proper user agent
- Hierarchical caching (session + persistent)
- Rate limiting and retry logic
- Context-aware search queries

**Usage:**
```python
service = GeocodingService(
    cache_dir=Path("./geocoding_cache"),
    rate_limit_delay=1.0,  # 1 second between requests
    max_retries=3,
    timeout=10
)

# Single location
result = service.geocode_location("New York City")

# Batch processing
results = service.batch_geocode([
    "San Francisco", 
    "Los Angeles", 
    "Seattle"
])
```

### LocationContext

Provides context information to improve geocoding accuracy.

```python
context = LocationContext(
    state="California",
    region="Bay Area", 
    country="United States"
)

result = service.geocode_location("Berkeley", context)
```

### InteractiveGeocodingCorrector

Handles manual corrections for failed geocoding attempts.

**Features:**
- Review geocoding results and failures
- Manual coordinate specification
- Bulk correction capabilities
- Validation of manual inputs
- Export/import corrections

**Usage:**
```python
corrector = InteractiveGeocodingCorrector(service)

# Get summary of results
summary = corrector.get_geocoding_summary(results)

# Add manual correction
corrector.add_manual_correction(
    location_name="Custom Location",
    latitude=37.7749,
    longitude=-122.4194,
    notes="Manual correction"
)

# Bulk corrections
corrections = [
    {
        "location_name": "Location 1",
        "latitude": 40.7128,
        "longitude": -74.0060
    },
    # ... more corrections
]
corrector.apply_bulk_corrections(corrections)
```

### BatchGeocodingProcessor

Processes large batches of locations with progress tracking and recovery.

**Features:**
- Progress saving and resumption
- Partial failure handling
- Time estimation and reporting
- Integration with interactive correction

**Usage:**
```python
processor = BatchGeocodingProcessor(service)

# Configure batch processing
config = BatchProcessingConfig(
    batch_size=50,
    save_progress_every=10,
    max_retries=3
)

# Process batch
state = processor.process_batch(
    locations=location_list,
    contexts=context_list,
    config=config,
    session_id="my_batch"
)

# Retry failed locations
state = processor.retry_failed_locations(state)

# Apply manual corrections
corrections = [...]  # Manual corrections
state = processor.apply_manual_corrections_to_batch(state, corrections)
```

## Configuration

### Rate Limiting

The service implements rate limiting to respect API limits:

```python
service = GeocodingService(
    rate_limit_delay=1.0,  # Minimum 1 second between requests
    max_retries=3,         # Retry failed requests up to 3 times
    timeout=10             # 10 second request timeout
)
```

### Caching

Caching is automatic and hierarchical:

- **Session cache**: In-memory cache for current session
- **Persistent cache**: File-based cache that persists between sessions
- **Cache organization**: Organized by location + context hash

```python
# Get cache statistics
stats = service.get_cache_stats()
print(f"Cached entries: {stats['cached_entries']}")
print(f"Cache size: {stats['cache_size_mb']:.2f} MB")

# Clear cache if needed
service.clear_cache()
```

## Error Handling

The service provides comprehensive error handling:

### Common Error Types

1. **Network errors**: Connection timeouts, DNS failures
2. **API errors**: Rate limiting, service unavailable
3. **Data errors**: Invalid responses, parsing failures
4. **Validation errors**: Invalid coordinates, malformed input

### Error Recovery

```python
# Check for failed locations
failed_locations = service.get_failed_locations()

for failed in failed_locations:
    print(f"Failed: {failed.location_name}")
    print(f"Error: {failed.error_message}")
    print(f"Attempts: {failed.attempts}")
    
    # Get suggestions for correction
    suggestions = corrector.get_correction_suggestions(failed)
    for suggestion in suggestions:
        print(f"  - {suggestion['description']}")
```

## Best Practices

### 1. Use Context Information

Always provide context when available to improve accuracy:

```python
context = LocationContext(
    state="California",
    region="San Francisco Bay Area",
    country="United States"
)
result = service.geocode_location("Berkeley", context)
```

### 2. Batch Processing for Large Datasets

Use batch processing for multiple locations:

```python
# Instead of individual calls
for location in locations:
    result = service.geocode_location(location)  # Don't do this

# Use batch processing
results = service.batch_geocode(locations, contexts)  # Do this
```

### 3. Handle Failures Gracefully

Always check for failures and provide fallbacks:

```python
result = service.geocode_location("Some Location")
if not result.success:
    # Log the error
    logger.warning(f"Geocoding failed for {result.location_name}: {result.error_message}")
    
    # Provide fallback or request manual input
    corrector.add_manual_correction(...)
```

### 4. Monitor Cache Performance

Regularly check cache statistics to ensure good performance:

```python
stats = service.get_cache_stats()
if stats['cache_size_mb'] > 100:  # 100 MB limit
    # Consider cleaning old cache entries
    service.clear_cache()
```

### 5. Respect Rate Limits

Configure appropriate rate limiting based on your usage:

```python
# For development/testing
service = GeocodingService(rate_limit_delay=0.5)

# For production with many requests
service = GeocodingService(rate_limit_delay=2.0)
```

## Integration with Road Trip Animator

The geocoding service integrates with the main road trip animator workflow:

```python
from road_trip_animator.data.importers import parse_itinerary_csv
from road_trip_animator.geocoding import GeocodingService, BatchGeocodingProcessor

# Parse itinerary data
entries = parse_itinerary_csv("trip_itinerary.csv")

# Extract locations and contexts
locations = [entry['location_name'] for entry in entries]
contexts = [
    LocationContext(
        state=entry.get('state'),
        region=entry.get('region')
    ) for entry in entries
]

# Geocode all locations
service = GeocodingService()
processor = BatchGeocodingProcessor(service)

state = processor.process_batch(locations, contexts)

# Handle any failures
if state.failed_count > 0:
    report = processor.generate_correction_report(state)
    # Present report to user for manual corrections
```

## API Reference

See the individual module docstrings for detailed API documentation:

- `service.py`: Core geocoding service
- `interactive.py`: Interactive correction functionality  
- `batch.py`: Batch processing capabilities

## Requirements

- Python 3.7+
- Internet connection for geocoding API calls
- Write access for cache directory (default: `~/.road_trip_animator/geocoding_cache`)

## External Services

The service uses OpenStreetMap's Nominatim service for geocoding:
- Base URL: `https://nominatim.openstreetmap.org/search`
- User Agent: `road_trip_map_animator`
- Rate Limiting: Respects Nominatim usage policy
- Documentation: https://nominatim.org/release-docs/develop/api/Search/