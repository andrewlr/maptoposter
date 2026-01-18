"""
Batch processing utilities for geocoding operations.

This module provides functionality for processing large batches of locations
with partial failure handling, progress tracking, and recovery capabilities.
"""

import logging
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime

from ..models import Coordinates
from .service import GeocodingService, GeocodingResult, LocationContext
from .interactive import InteractiveGeocodingCorrector


logger = logging.getLogger(__name__)


@dataclass
class BatchProcessingConfig:
    """Configuration for batch geocoding operations."""
    batch_size: int = 50
    save_progress_every: int = 10
    max_retries: int = 3
    retry_delay: float = 5.0
    progress_callback: Optional[Callable[[int, int, int], None]] = None
    
    def __post_init__(self):
        """Validate configuration."""
        if self.batch_size <= 0:
            raise ValueError("Batch size must be positive")
        if self.save_progress_every <= 0:
            raise ValueError("Save progress interval must be positive")
        if self.max_retries < 0:
            raise ValueError("Max retries must be non-negative")
        if self.retry_delay < 0:
            raise ValueError("Retry delay must be non-negative")


@dataclass
class BatchProcessingState:
    """State tracking for batch processing operations."""
    total_locations: int
    processed_count: int = 0
    successful_count: int = 0
    failed_count: int = 0
    current_batch: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    last_save_time: datetime = field(default_factory=datetime.now)
    results: List[GeocodingResult] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for JSON serialization."""
        return {
            "total_locations": self.total_locations,
            "processed_count": self.processed_count,
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "current_batch": self.current_batch,
            "start_time": self.start_time.isoformat(),
            "last_save_time": self.last_save_time.isoformat(),
            "results": [
                {
                    "location_name": r.location_name,
                    "success": r.success,
                    "coordinates": {
                        "latitude": r.coordinates.latitude,
                        "longitude": r.coordinates.longitude
                    } if r.coordinates else None,
                    "error_message": r.error_message,
                    "confidence": r.confidence,
                    "display_name": r.display_name
                }
                for r in self.results
            ]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BatchProcessingState':
        """Create state from dictionary."""
        results = []
        for result_data in data.get("results", []):
            coordinates = None
            if result_data.get("coordinates"):
                coord_data = result_data["coordinates"]
                coordinates = Coordinates(
                    latitude=coord_data["latitude"],
                    longitude=coord_data["longitude"]
                )
            
            result = GeocodingResult(
                location_name=result_data["location_name"],
                coordinates=coordinates,
                success=result_data["success"],
                error_message=result_data.get("error_message"),
                confidence=result_data.get("confidence", 0.0),
                display_name=result_data.get("display_name")
            )
            results.append(result)
        
        return cls(
            total_locations=data["total_locations"],
            processed_count=data["processed_count"],
            successful_count=data["successful_count"],
            failed_count=data["failed_count"],
            current_batch=data["current_batch"],
            start_time=datetime.fromisoformat(data["start_time"]),
            last_save_time=datetime.fromisoformat(data["last_save_time"]),
            results=results
        )


class BatchGeocodingProcessor:
    """
    Batch processor for geocoding operations with progress tracking and recovery.
    
    Features:
    - Process large batches of locations efficiently
    - Save progress periodically for recovery
    - Handle partial failures gracefully
    - Integrate with interactive correction system
    - Provide detailed progress reporting
    """
    
    def __init__(self, 
                 geocoding_service: GeocodingService,
                 interactive_corrector: Optional[InteractiveGeocodingCorrector] = None,
                 progress_dir: Optional[Path] = None):
        """
        Initialize the batch processor.
        
        Args:
            geocoding_service: The geocoding service to use
            interactive_corrector: Optional interactive corrector for failed locations
            progress_dir: Directory for saving progress files
        """
        self.geocoding_service = geocoding_service
        self.interactive_corrector = interactive_corrector or InteractiveGeocodingCorrector(geocoding_service)
        self.progress_dir = progress_dir or Path.home() / ".road_trip_animator" / "batch_progress"
        self.progress_dir.mkdir(parents=True, exist_ok=True)
    
    def _save_progress(self, state: BatchProcessingState, session_id: str) -> None:
        """Save processing progress to file."""
        try:
            progress_file = self.progress_dir / f"batch_{session_id}.json"
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
            
            state.last_save_time = datetime.now()
            logger.debug(f"Saved progress to {progress_file}")
            
        except (OSError, json.JSONEncodeError) as e:
            logger.error(f"Failed to save progress: {e}")
    
    def _load_progress(self, session_id: str) -> Optional[BatchProcessingState]:
        """Load processing progress from file."""
        try:
            progress_file = self.progress_dir / f"batch_{session_id}.json"
            if not progress_file.exists():
                return None
            
            with open(progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            state = BatchProcessingState.from_dict(data)
            logger.info(f"Loaded progress from {progress_file}: {state.processed_count}/{state.total_locations} processed")
            return state
            
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to load progress: {e}")
            return None
    
    def _cleanup_progress(self, session_id: str) -> None:
        """Clean up progress file after successful completion."""
        try:
            progress_file = self.progress_dir / f"batch_{session_id}.json"
            progress_file.unlink(missing_ok=True)
            logger.debug(f"Cleaned up progress file: {progress_file}")
        except OSError as e:
            logger.warning(f"Failed to cleanup progress file: {e}")
    
    def process_batch(self, 
                     locations: List[str],
                     contexts: Optional[List[LocationContext]] = None,
                     config: Optional[BatchProcessingConfig] = None,
                     session_id: Optional[str] = None,
                     resume: bool = True) -> BatchProcessingState:
        """
        Process a batch of locations with progress tracking and recovery.
        
        Args:
            locations: List of location names to geocode
            contexts: Optional list of context information
            config: Batch processing configuration
            session_id: Unique session identifier for progress tracking
            resume: Whether to resume from saved progress
            
        Returns:
            BatchProcessingState with final results
        """
        if not locations:
            raise ValueError("Locations list cannot be empty")
        
        if contexts and len(contexts) != len(locations):
            raise ValueError("Contexts list must match locations list length")
        
        config = config or BatchProcessingConfig()
        session_id = session_id or f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Try to resume from saved progress
        state = None
        if resume:
            state = self._load_progress(session_id)
        
        # Initialize new state if no saved progress
        if state is None:
            state = BatchProcessingState(total_locations=len(locations))
            logger.info(f"Starting new batch processing session: {session_id}")
        else:
            logger.info(f"Resuming batch processing session: {session_id}")
        
        # Process remaining locations
        remaining_locations = locations[state.processed_count:]
        remaining_contexts = contexts[state.processed_count:] if contexts else None
        
        try:
            for i, location in enumerate(remaining_locations):
                current_index = state.processed_count + i
                context = remaining_contexts[i] if remaining_contexts else None
                
                # Progress callback
                if config.progress_callback:
                    config.progress_callback(current_index + 1, state.total_locations, state.successful_count)
                
                logger.debug(f"Processing {current_index + 1}/{state.total_locations}: {location}")
                
                # Geocode location
                result = self.geocoding_service.geocode_location(location, context)
                state.results.append(result)
                
                # Update counters
                state.processed_count += 1
                if result.success:
                    state.successful_count += 1
                else:
                    state.failed_count += 1
                
                # Save progress periodically
                if (current_index + 1) % config.save_progress_every == 0:
                    self._save_progress(state, session_id)
                    logger.info(f"Progress: {state.processed_count}/{state.total_locations} processed, "
                              f"{state.successful_count} successful, {state.failed_count} failed")
        
        except KeyboardInterrupt:
            logger.info("Batch processing interrupted by user")
            self._save_progress(state, session_id)
            raise
        
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            self._save_progress(state, session_id)
            raise
        
        # Final progress save and cleanup
        self._save_progress(state, session_id)
        
        # Log final results
        duration = datetime.now() - state.start_time
        logger.info(f"Batch processing complete: {state.successful_count}/{state.total_locations} successful "
                   f"({state.successful_count/state.total_locations:.1%}) in {duration}")
        
        # Clean up progress file on successful completion
        if state.processed_count == state.total_locations:
            self._cleanup_progress(session_id)
        
        return state
    
    def retry_failed_locations(self, 
                              state: BatchProcessingState,
                              config: Optional[BatchProcessingConfig] = None) -> BatchProcessingState:
        """
        Retry geocoding for failed locations.
        
        Args:
            state: Previous batch processing state
            config: Batch processing configuration
            
        Returns:
            Updated BatchProcessingState with retry results
        """
        config = config or BatchProcessingConfig()
        
        # Extract failed locations
        failed_results = [r for r in state.results if not r.success]
        if not failed_results:
            logger.info("No failed locations to retry")
            return state
        
        logger.info(f"Retrying {len(failed_results)} failed locations")
        
        # Create new locations list for retry
        retry_locations = [r.location_name for r in failed_results]
        retry_contexts = [r.context_used for r in failed_results]
        
        # Process retries
        retry_state = self.process_batch(
            locations=retry_locations,
            contexts=retry_contexts,
            config=config,
            session_id=f"retry_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            resume=False
        )
        
        # Update original results with retry results
        retry_results_map = {r.location_name: r for r in retry_state.results}
        
        updated_results = []
        for original_result in state.results:
            if not original_result.success and original_result.location_name in retry_results_map:
                # Use retry result
                retry_result = retry_results_map[original_result.location_name]
                updated_results.append(retry_result)
                
                # Update counters
                if retry_result.success and not original_result.success:
                    state.successful_count += 1
                    state.failed_count -= 1
            else:
                # Keep original result
                updated_results.append(original_result)
        
        state.results = updated_results
        
        logger.info(f"Retry complete: {retry_state.successful_count}/{len(failed_results)} "
                   f"previously failed locations now successful")
        
        return state
    
    def generate_correction_report(self, state: BatchProcessingState) -> Dict[str, Any]:
        """
        Generate a report for manual correction of failed locations.
        
        Args:
            state: Batch processing state
            
        Returns:
            Dictionary containing correction report
        """
        failed_results = [r for r in state.results if not r.success]
        
        report = {
            "summary": self.interactive_corrector.get_geocoding_summary(state.results),
            "failed_locations": [],
            "suggestions": []
        }
        
        for result in failed_results:
            failed_geocoding = self.geocoding_service.get_failed_locations()
            matching_failed = [
                f for f in failed_geocoding 
                if f.location_name == result.location_name
            ]
            
            if matching_failed:
                failed_location = matching_failed[0]
                suggestions = self.interactive_corrector.get_correction_suggestions(failed_location)
                
                report["failed_locations"].append({
                    "location_name": result.location_name,
                    "error_message": result.error_message,
                    "context": {
                        "state": result.context_used.state if result.context_used else None,
                        "region": result.context_used.region if result.context_used else None,
                        "country": result.context_used.country if result.context_used else None
                    },
                    "suggestions": suggestions
                })
        
        return report
    
    def apply_manual_corrections_to_batch(self, 
                                        state: BatchProcessingState,
                                        corrections: List[Dict[str, Any]]) -> BatchProcessingState:
        """
        Apply manual corrections to a batch processing state.
        
        Args:
            state: Batch processing state to update
            corrections: List of manual corrections
            
        Returns:
            Updated BatchProcessingState
        """
        # Apply corrections to interactive corrector
        correction_results = self.interactive_corrector.apply_bulk_corrections(corrections)
        
        # Update batch state results
        correction_map = {}
        for i, correction in enumerate(corrections):
            if correction_results[i]:  # Successful correction
                location_name = correction['location_name']
                coordinates = Coordinates(
                    latitude=float(correction['latitude']),
                    longitude=float(correction['longitude'])
                )
                
                # Create corrected result
                corrected_result = GeocodingResult(
                    location_name=location_name,
                    coordinates=coordinates,
                    success=True,
                    confidence=1.0,  # Manual corrections have highest confidence
                    display_name=f"{location_name} (manual)",
                    context_used=None  # Context handled by correction
                )
                
                correction_map[location_name] = corrected_result
        
        # Update results in state
        updated_results = []
        for result in state.results:
            if not result.success and result.location_name in correction_map:
                # Use corrected result
                corrected_result = correction_map[result.location_name]
                updated_results.append(corrected_result)
                
                # Update counters
                state.successful_count += 1
                state.failed_count -= 1
            else:
                # Keep original result
                updated_results.append(result)
        
        state.results = updated_results
        
        successful_corrections = sum(correction_results)
        logger.info(f"Applied {successful_corrections} manual corrections to batch state")
        
        return state
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """
        Get list of active (incomplete) batch processing sessions.
        
        Returns:
            List of session information dictionaries
        """
        sessions = []
        
        for progress_file in self.progress_dir.glob("batch_*.json"):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                session_info = {
                    "session_id": progress_file.stem.replace("batch_", ""),
                    "file_path": str(progress_file),
                    "total_locations": data["total_locations"],
                    "processed_count": data["processed_count"],
                    "successful_count": data["successful_count"],
                    "failed_count": data["failed_count"],
                    "start_time": data["start_time"],
                    "last_save_time": data["last_save_time"],
                    "progress_percent": (data["processed_count"] / data["total_locations"]) * 100
                }
                
                sessions.append(session_info)
                
            except (OSError, json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to read progress file {progress_file}: {e}")
        
        # Sort by last save time (most recent first)
        sessions.sort(key=lambda x: x["last_save_time"], reverse=True)
        
        return sessions