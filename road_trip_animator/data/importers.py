"""
Data import functionality for the Road Trip Animator.

This module provides importers for various data formats including CSV itineraries,
GPX files, and JSON route data. It handles parsing, validation, and conversion
to the internal data models.
"""

import csv
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
import re

from ..models import Waypoint, Route, RouteSegment, Coordinates
from ..validation import ValidationError, validate_coordinate_range


class ImportError(Exception):
    """Custom exception for data import errors."""
    pass


class CSVItineraryParser:
    """
    Parser for travel spreadsheet CSV format.
    
    Expected columns: Month, Date, Day, Week, State, Region, Location, Booking Notes, Accommodation
    """
    
    REQUIRED_COLUMNS = ['Month', 'Date', 'Location']
    OPTIONAL_COLUMNS = ['Day', 'Week', 'State', 'Region', 'Booking Notes', 'Accommodation']
    ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def parse_file(self, file_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Parse CSV itinerary file.
        
        Args:
            file_path: Path to CSV file
            
        Returns:
            List of parsed itinerary entries
            
        Raises:
            ImportError: If file cannot be parsed or has critical errors
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise ImportError(f"File not found: {file_path}")
        
        self.errors = []
        self.warnings = []
        entries = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                # Try to detect delimiter
                sample = csvfile.read(1024)
                csvfile.seek(0)
                
                delimiter = ','
                if sample.count(';') > sample.count(','):
                    delimiter = ';'
                elif sample.count('\t') > sample.count(','):
                    delimiter = '\t'
                
                reader = csv.DictReader(csvfile, delimiter=delimiter)
                
                # Validate headers
                self._validate_headers(reader.fieldnames)
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 because header is row 1
                    try:
                        entry = self._parse_row(row, row_num)
                        if entry:
                            entries.append(entry)
                    except Exception as e:
                        self.errors.append(f"Line {row_num}: {str(e)}")
        
        except Exception as e:
            raise ImportError(f"Failed to read CSV file: {str(e)}")
        
        if self.errors:
            error_summary = f"Found {len(self.errors)} errors:\n" + "\n".join(self.errors[:10])
            if len(self.errors) > 10:
                error_summary += f"\n... and {len(self.errors) - 10} more errors"
            raise ImportError(error_summary)
        
        if not entries:
            raise ImportError("No valid entries found in CSV file")
        
        return entries
    
    def _validate_headers(self, headers: List[str]) -> None:
        """Validate CSV headers contain required columns."""
        if not headers:
            raise ImportError("CSV file has no headers")
        
        # Normalize headers (case-insensitive, strip whitespace)
        normalized_headers = [h.strip().lower() if h else '' for h in headers]
        required_normalized = [col.lower() for col in self.REQUIRED_COLUMNS]
        
        missing_columns = []
        for required_col in required_normalized:
            if required_col not in normalized_headers:
                missing_columns.append(required_col.title())
        
        if missing_columns:
            raise ImportError(f"Missing required columns: {', '.join(missing_columns)}")
    
    def _parse_row(self, row: Dict[str, str], row_num: int) -> Optional[Dict[str, Any]]:
        """
        Parse a single CSV row into an itinerary entry.
        
        Args:
            row: CSV row data
            row_num: Row number for error reporting
            
        Returns:
            Parsed entry dictionary or None if row should be skipped
        """
        # Normalize column names (case-insensitive)
        normalized_row = {}
        for key, value in row.items():
            if key:
                normalized_key = key.strip().lower()
                # Map common variations
                if normalized_key in ['month']:
                    normalized_row['month'] = value.strip() if value else ''
                elif normalized_key in ['date']:
                    normalized_row['date'] = value.strip() if value else ''
                elif normalized_key in ['day']:
                    normalized_row['day'] = value.strip() if value else ''
                elif normalized_key in ['week']:
                    normalized_row['week'] = value.strip() if value else ''
                elif normalized_key in ['state']:
                    normalized_row['state'] = value.strip() if value else ''
                elif normalized_key in ['region']:
                    normalized_row['region'] = value.strip() if value else ''
                elif normalized_key in ['location']:
                    normalized_row['location'] = value.strip() if value else ''
                elif normalized_key in ['booking notes', 'booking_notes', 'notes']:
                    normalized_row['booking_notes'] = value.strip() if value else ''
                elif normalized_key in ['accommodation']:
                    normalized_row['accommodation'] = value.strip() if value else ''
        
        # Skip empty rows
        if not any(normalized_row.values()):
            return None
        
        # Validate required fields
        if not normalized_row.get('location'):
            raise ImportError(f"Missing location")
        
        # Parse date
        try:
            timestamp = self._parse_date(normalized_row.get('month', ''), 
                                       normalized_row.get('date', ''), 
                                       row_num)
        except Exception as e:
            raise ImportError(f"Date parsing error: {str(e)}")
        
        return {
            'timestamp': timestamp,
            'location_name': normalized_row['location'],
            'state': normalized_row.get('state') or None,
            'region': normalized_row.get('region') or None,
            'accommodation': normalized_row.get('accommodation') or None,
            'notes': normalized_row.get('booking_notes') or None,
            'day': normalized_row.get('day') or None,
            'week': normalized_row.get('week') or None,
            'raw_month': normalized_row.get('month', ''),
            'raw_date': normalized_row.get('date', ''),
            'row_number': row_num
        }
    
    def _parse_date(self, month_str: str, date_str: str, row_num: int) -> datetime:
        """
        Parse date from Month and Date columns.
        
        Args:
            month_str: Month string (e.g., "January", "Jan", "1")
            date_str: Date string (e.g., "15", "2023-01-15")
            row_num: Row number for error reporting
            
        Returns:
            Parsed datetime object
        """
        if not month_str and not date_str:
            raise ValueError("Both month and date are empty")
        
        # If date_str looks like a full date, try parsing it directly
        if date_str and len(date_str) > 5 and ('-' in date_str or '/' in date_str):
            try:
                # Try common date formats
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d']:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except ValueError:
                        continue
            except:
                pass
        
        # Parse month
        month_num = self._parse_month(month_str)
        if month_num is None:
            raise ValueError(f"Invalid month: '{month_str}'")
        
        # Parse day
        day_num = self._parse_day(date_str)
        if day_num is None:
            raise ValueError(f"Invalid date: '{date_str}'")
        
        # Use current year as default (could be made configurable)
        year = datetime.now().year
        
        # Try to create the date
        try:
            return datetime(year, month_num, day_num)
        except ValueError as e:
            raise ValueError(f"Invalid date {year}-{month_num:02d}-{day_num:02d}: {str(e)}")
    
    def _parse_month(self, month_str: str) -> Optional[int]:
        """Parse month string to month number (1-12)."""
        if not month_str:
            return None
        
        month_str = month_str.strip().lower()
        
        # Try numeric month
        try:
            month_num = int(month_str)
            if 1 <= month_num <= 12:
                return month_num
        except ValueError:
            pass
        
        # Try month names
        month_names = {
            'january': 1, 'jan': 1,
            'february': 2, 'feb': 2,
            'march': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'may': 5,
            'june': 6, 'jun': 6,
            'july': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12
        }
        
        return month_names.get(month_str)
    
    def _parse_day(self, date_str: str) -> Optional[int]:
        """Parse day string to day number (1-31)."""
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Try direct numeric conversion
        try:
            day_num = int(date_str)
            if 1 <= day_num <= 31:
                return day_num
        except ValueError:
            pass
        
        # Try extracting number from string (e.g., "15th" -> 15)
        match = re.search(r'\d+', date_str)
        if match:
            try:
                day_num = int(match.group())
                if 1 <= day_num <= 31:
                    return day_num
            except ValueError:
                pass
        
        return None
    
    def get_errors(self) -> List[str]:
        """Get list of parsing errors."""
        return self.errors.copy()
    
    def get_warnings(self) -> List[str]:
        """Get list of parsing warnings."""
        return self.warnings.copy()


def create_waypoints_from_itinerary(entries: List[Dict[str, Any]]) -> List[Waypoint]:
    """
    Convert parsed itinerary entries to waypoints.
    
    Note: This function creates waypoints with placeholder coordinates (0, 0)
    since geocoding will be handled by a separate service.
    
    Args:
        entries: List of parsed itinerary entries
        
    Returns:
        List of waypoints with placeholder coordinates
    """
    waypoints = []
    
    for entry in entries:
        waypoint = Waypoint(
            latitude=0.0,  # Placeholder - will be filled by geocoding service
            longitude=0.0,  # Placeholder - will be filled by geocoding service
            timestamp=entry['timestamp'],
            location_name=entry['location_name'],
            state=entry.get('state'),
            region=entry.get('region'),
            accommodation=entry.get('accommodation'),
            notes=entry.get('notes')
        )
        waypoints.append(waypoint)
    
    # Sort waypoints chronologically
    waypoints.sort(key=lambda wp: wp.timestamp)
    
    return waypoints


class GPXParser:
    """
    Parser for GPX (GPS Exchange Format) files.
    
    Extracts track points with coordinates and timestamps from GPX files.
    """
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def parse_file(self, file_path: Union[str, Path]) -> List[Waypoint]:
        """
        Parse GPX file and extract waypoints.
        
        Args:
            file_path: Path to GPX file
            
        Returns:
            List of waypoints with coordinates and timestamps
            
        Raises:
            ImportError: If file cannot be parsed or has critical errors
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise ImportError(f"File not found: {file_path}")
        
        self.errors = []
        self.warnings = []
        waypoints = []
        
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Handle namespace
            namespace = ''
            if root.tag.startswith('{'):
                namespace = root.tag.split('}')[0] + '}'
            
            # Extract track points
            trkpts = root.findall(f'.//{namespace}trkpt')
            if not trkpts:
                # Try waypoints if no track points
                trkpts = root.findall(f'.//{namespace}wpt')
            
            if not trkpts:
                raise ImportError("No track points or waypoints found in GPX file")
            
            for i, trkpt in enumerate(trkpts):
                try:
                    waypoint = self._parse_track_point(trkpt, namespace, i + 1)
                    if waypoint:
                        waypoints.append(waypoint)
                except Exception as e:
                    self.errors.append(f"Track point {i + 1}: {str(e)}")
        
        except ET.ParseError as e:
            raise ImportError(f"Invalid GPX file format: {str(e)}")
        except Exception as e:
            raise ImportError(f"Failed to parse GPX file: {str(e)}")
        
        if self.errors:
            error_summary = f"Found {len(self.errors)} errors:\n" + "\n".join(self.errors[:10])
            if len(self.errors) > 10:
                error_summary += f"\n... and {len(self.errors) - 10} more errors"
            raise ImportError(error_summary)
        
        if not waypoints:
            raise ImportError("No valid waypoints found in GPX file")
        
        # Sort waypoints chronologically
        waypoints.sort(key=lambda wp: wp.timestamp)
        
        return waypoints
    
    def _parse_track_point(self, trkpt, namespace: str, point_num: int) -> Optional[Waypoint]:
        """Parse a single track point element."""
        # Get coordinates
        lat_str = trkpt.get('lat')
        lon_str = trkpt.get('lon')
        
        if not lat_str or not lon_str:
            raise ValueError("Missing latitude or longitude")
        
        try:
            latitude = float(lat_str)
            longitude = float(lon_str)
            validate_coordinate_range(latitude, longitude)
        except (ValueError, ValidationError) as e:
            raise ValueError(f"Invalid coordinates: {str(e)}")
        
        # Get timestamp
        time_elem = trkpt.find(f'{namespace}time')
        if time_elem is not None and time_elem.text:
            try:
                # Parse ISO 8601 timestamp
                timestamp_str = time_elem.text.strip()
                # Handle different timestamp formats
                if timestamp_str.endswith('Z'):
                    timestamp = datetime.fromisoformat(timestamp_str[:-1])
                elif '+' in timestamp_str or timestamp_str.count('-') > 2:
                    # Handle timezone info
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError as e:
                raise ValueError(f"Invalid timestamp format: {str(e)}")
        else:
            # Use current time if no timestamp (with warning)
            timestamp = datetime.now()
            self.warnings.append(f"Track point {point_num}: No timestamp found, using current time")
        
        # Get name/description
        name_elem = trkpt.find(f'{namespace}name')
        desc_elem = trkpt.find(f'{namespace}desc')
        
        location_name = ""
        if name_elem is not None and name_elem.text:
            location_name = name_elem.text.strip()
        elif desc_elem is not None and desc_elem.text:
            location_name = desc_elem.text.strip()
        else:
            location_name = f"Track Point {point_num}"
        
        # Get elevation (optional)
        ele_elem = trkpt.find(f'{namespace}ele')
        notes = ""
        if ele_elem is not None and ele_elem.text:
            try:
                elevation = float(ele_elem.text)
                notes = f"Elevation: {elevation}m"
            except ValueError:
                pass
        
        return Waypoint(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp,
            location_name=location_name,
            notes=notes if notes else None
        )
    
    def get_errors(self) -> List[str]:
        """Get list of parsing errors."""
        return self.errors.copy()
    
    def get_warnings(self) -> List[str]:
        """Get list of parsing warnings."""
        return self.warnings.copy()


class JSONRouteParser:
    """
    Parser for JSON route data format.
    
    Expected format:
    {
        "waypoints": [
            {
                "latitude": float,
                "longitude": float,
                "timestamp": "ISO 8601 string",
                "location_name": "string",
                "state": "optional string",
                "region": "optional string",
                "accommodation": "optional string",
                "notes": "optional string"
            }
        ],
        "route_overrides": [
            {
                "start_index": int,
                "end_index": int,
                "custom_path": [
                    {"latitude": float, "longitude": float}
                ]
            }
        ]
    }
    """
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def parse_file(self, file_path: Union[str, Path]) -> Tuple[List[Waypoint], List[Dict[str, Any]]]:
        """
        Parse JSON route file.
        
        Args:
            file_path: Path to JSON file
            
        Returns:
            Tuple of (waypoints, route_overrides)
            
        Raises:
            ImportError: If file cannot be parsed or has critical errors
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise ImportError(f"File not found: {file_path}")
        
        self.errors = []
        self.warnings = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as jsonfile:
                data = json.load(jsonfile)
        except json.JSONDecodeError as e:
            raise ImportError(f"Invalid JSON format: {str(e)}")
        except Exception as e:
            raise ImportError(f"Failed to read JSON file: {str(e)}")
        
        # Validate top-level structure
        if not isinstance(data, dict):
            raise ImportError("JSON root must be an object")
        
        if 'waypoints' not in data:
            raise ImportError("JSON must contain 'waypoints' array")
        
        if not isinstance(data['waypoints'], list):
            raise ImportError("'waypoints' must be an array")
        
        # Parse waypoints
        waypoints = []
        for i, wp_data in enumerate(data['waypoints']):
            try:
                waypoint = self._parse_waypoint(wp_data, i + 1)
                waypoints.append(waypoint)
            except Exception as e:
                self.errors.append(f"Waypoint {i + 1}: {str(e)}")
        
        # Parse route overrides (optional)
        route_overrides = []
        if 'route_overrides' in data:
            if not isinstance(data['route_overrides'], list):
                self.warnings.append("'route_overrides' should be an array, ignoring")
            else:
                for i, override_data in enumerate(data['route_overrides']):
                    try:
                        override = self._parse_route_override(override_data, i + 1, len(waypoints))
                        route_overrides.append(override)
                    except Exception as e:
                        self.errors.append(f"Route override {i + 1}: {str(e)}")
        
        if self.errors:
            error_summary = f"Found {len(self.errors)} errors:\n" + "\n".join(self.errors[:10])
            if len(self.errors) > 10:
                error_summary += f"\n... and {len(self.errors) - 10} more errors"
            raise ImportError(error_summary)
        
        if not waypoints:
            raise ImportError("No valid waypoints found in JSON file")
        
        # Sort waypoints chronologically
        waypoints.sort(key=lambda wp: wp.timestamp)
        
        return waypoints, route_overrides
    
    def _parse_waypoint(self, wp_data: Dict[str, Any], wp_num: int) -> Waypoint:
        """Parse a single waypoint from JSON data."""
        if not isinstance(wp_data, dict):
            raise ValueError("Waypoint must be an object")
        
        # Required fields
        required_fields = ['latitude', 'longitude', 'timestamp', 'location_name']
        for field in required_fields:
            if field not in wp_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Parse coordinates
        try:
            latitude = float(wp_data['latitude'])
            longitude = float(wp_data['longitude'])
            validate_coordinate_range(latitude, longitude)
        except (ValueError, ValidationError) as e:
            raise ValueError(f"Invalid coordinates: {str(e)}")
        
        # Parse timestamp
        try:
            timestamp_str = wp_data['timestamp']
            if isinstance(timestamp_str, str):
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                raise ValueError("Timestamp must be a string")
        except ValueError as e:
            raise ValueError(f"Invalid timestamp: {str(e)}")
        
        # Parse location name
        location_name = wp_data['location_name']
        if not isinstance(location_name, str) or not location_name.strip():
            raise ValueError("Location name must be a non-empty string")
        
        # Optional fields
        state = wp_data.get('state')
        if state is not None and not isinstance(state, str):
            raise ValueError("State must be a string")
        
        region = wp_data.get('region')
        if region is not None and not isinstance(region, str):
            raise ValueError("Region must be a string")
        
        accommodation = wp_data.get('accommodation')
        if accommodation is not None and not isinstance(accommodation, str):
            raise ValueError("Accommodation must be a string")
        
        notes = wp_data.get('notes')
        if notes is not None and not isinstance(notes, str):
            raise ValueError("Notes must be a string")
        
        return Waypoint(
            latitude=latitude,
            longitude=longitude,
            timestamp=timestamp,
            location_name=location_name.strip(),
            state=state.strip() if state else None,
            region=region.strip() if region else None,
            accommodation=accommodation.strip() if accommodation else None,
            notes=notes.strip() if notes else None
        )
    
    def _parse_route_override(self, override_data: Dict[str, Any], override_num: int, total_waypoints: int) -> Dict[str, Any]:
        """Parse a route override from JSON data."""
        if not isinstance(override_data, dict):
            raise ValueError("Route override must be an object")
        
        # Required fields
        required_fields = ['start_index', 'end_index', 'custom_path']
        for field in required_fields:
            if field not in override_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Parse indices
        try:
            start_index = int(override_data['start_index'])
            end_index = int(override_data['end_index'])
        except ValueError:
            raise ValueError("start_index and end_index must be integers")
        
        # Validate indices
        if start_index < 0 or start_index >= total_waypoints:
            raise ValueError(f"start_index {start_index} is out of range (0-{total_waypoints-1})")
        if end_index < 0 or end_index >= total_waypoints:
            raise ValueError(f"end_index {end_index} is out of range (0-{total_waypoints-1})")
        if start_index >= end_index:
            raise ValueError("start_index must be less than end_index")
        
        # Parse custom path
        custom_path_data = override_data['custom_path']
        if not isinstance(custom_path_data, list):
            raise ValueError("custom_path must be an array")
        
        custom_path = []
        for i, coord_data in enumerate(custom_path_data):
            if not isinstance(coord_data, dict):
                raise ValueError(f"Custom path coordinate {i + 1} must be an object")
            
            if 'latitude' not in coord_data or 'longitude' not in coord_data:
                raise ValueError(f"Custom path coordinate {i + 1} missing latitude or longitude")
            
            try:
                lat = float(coord_data['latitude'])
                lon = float(coord_data['longitude'])
                validate_coordinate_range(lat, lon)
                custom_path.append(Coordinates(lat, lon))
            except (ValueError, ValidationError) as e:
                raise ValueError(f"Custom path coordinate {i + 1}: {str(e)}")
        
        if not custom_path:
            raise ValueError("custom_path cannot be empty")
        
        return {
            'start_index': start_index,
            'end_index': end_index,
            'custom_path': custom_path
        }
    
    def get_errors(self) -> List[str]:
        """Get list of parsing errors."""
        return self.errors.copy()
    
    def get_warnings(self) -> List[str]:
        """Get list of parsing warnings."""
        return self.warnings.copy()


class UnifiedDataImporter:
    """
    Unified interface for importing data from multiple formats.
    
    Automatically detects file format and uses appropriate parser.
    """
    
    def __init__(self):
        self.csv_parser = CSVItineraryParser()
        self.gpx_parser = GPXParser()
        self.json_parser = JSONRouteParser()
    
    def import_file(self, file_path: Union[str, Path]) -> Tuple[List[Waypoint], List[Dict[str, Any]]]:
        """
        Import data from file, auto-detecting format.
        
        Args:
            file_path: Path to data file
            
        Returns:
            Tuple of (waypoints, route_overrides)
            route_overrides will be empty list for CSV and GPX formats
            
        Raises:
            ImportError: If file cannot be parsed or format not supported
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise ImportError(f"File not found: {file_path}")
        
        suffix = file_path.suffix.lower()
        
        if suffix == '.csv':
            entries = self.csv_parser.parse_file(file_path)
            waypoints = create_waypoints_from_itinerary(entries)
            return waypoints, []
        
        elif suffix == '.gpx':
            waypoints = self.gpx_parser.parse_file(file_path)
            return waypoints, []
        
        elif suffix == '.json':
            waypoints, route_overrides = self.json_parser.parse_file(file_path)
            return waypoints, route_overrides
        
        else:
            raise ImportError(f"Unsupported file format: {suffix}. Supported formats: .csv, .gpx, .json")
    
    def get_all_errors(self) -> Dict[str, List[str]]:
        """Get errors from all parsers."""
        return {
            'csv': self.csv_parser.get_errors(),
            'gpx': self.gpx_parser.get_errors(),
            'json': self.json_parser.get_errors()
        }
    
    def get_all_warnings(self) -> Dict[str, List[str]]:
        """Get warnings from all parsers."""
        return {
            'csv': self.csv_parser.get_warnings(),
            'gpx': self.gpx_parser.get_warnings(),
            'json': self.json_parser.get_warnings()
        }


def validate_itinerary_data(entries: List[Dict[str, Any]]) -> List[str]:
    """
    Validate parsed itinerary data for common issues.
    
    Args:
        entries: List of parsed itinerary entries
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    if not entries:
        errors.append("No entries found")
        return errors
    
    # Check for duplicate timestamps
    timestamps = [entry['timestamp'] for entry in entries]
    seen_timestamps = set()
    for i, timestamp in enumerate(timestamps):
        if timestamp in seen_timestamps:
            errors.append(f"Duplicate timestamp found: {timestamp} (entry {i+1})")
        seen_timestamps.add(timestamp)
    
    # Check for empty location names
    for i, entry in enumerate(entries):
        if not entry.get('location_name', '').strip():
            errors.append(f"Entry {i+1}: Empty location name")
    
    # Check chronological order
    for i in range(1, len(entries)):
        if entries[i]['timestamp'] < entries[i-1]['timestamp']:
            errors.append(
                f"Entry {i+1} ({entries[i]['location_name']}) is before entry {i} "
                f"({entries[i-1]['location_name']}) chronologically"
            )
    
    return errors


def validate_waypoints(waypoints: List[Waypoint]) -> List[str]:
    """
    Validate waypoints for common issues.
    
    Args:
        waypoints: List of waypoints to validate
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    if not waypoints:
        errors.append("No waypoints found")
        return errors
    
    # Check for duplicate timestamps
    timestamps = [wp.timestamp for wp in waypoints]
    seen_timestamps = set()
    for i, timestamp in enumerate(timestamps):
        if timestamp in seen_timestamps:
            errors.append(f"Duplicate timestamp found: {timestamp} (waypoint {i+1}: {waypoints[i].location_name})")
        seen_timestamps.add(timestamp)
    
    # Check for duplicate locations at same time
    location_times = [(wp.latitude, wp.longitude, wp.timestamp) for wp in waypoints]
    seen_location_times = set()
    for i, location_time in enumerate(location_times):
        if location_time in seen_location_times:
            errors.append(f"Duplicate location and timestamp found: waypoint {i+1} ({waypoints[i].location_name})")
        seen_location_times.add(location_time)
    
    # Check chronological order
    for i in range(1, len(waypoints)):
        if waypoints[i].timestamp < waypoints[i-1].timestamp:
            errors.append(
                f"Waypoint {i+1} ({waypoints[i].location_name}) is before waypoint {i} "
                f"({waypoints[i-1].location_name}) chronologically"
            )
    
    return errors