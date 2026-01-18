"""
Integrated cache and rate limiting manager.

This module provides a unified interface that combines hierarchical geographic
data caching with API rate limiting for comprehensive data management.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta

from .manager import CacheManager
from .rate_limiter import RateLimitManager, ServiceType
from .models import BoundingBox, CacheLevel, RouteBufferConfig


logger = logging.getLogger(__name__)


class IntegratedCacheManager:
    """
    Integrated manager combining hierarchical caching with API rate limiting.
    
    This class provides a unified interface for managing geographic data
    with automatic caching, rate limiting, and intelligent data acquisition.
    """
    
    def __init__(self, cache_dir: str, max_cache_size_mb: int = 1000,
                 rate_limit_config_file: Optional[str] = None):
        """
        Initialize the integrated cache manager.
        
        Args:
            cache_dir: Directory for cache storage
            max_cache_size_mb: Maximum cache size in megabytes
            rate_limit_config_file: Optional rate limiting configuration file
        """
        self.cache_manager = CacheManager(
            cache_dir=cache_dir,
            max_cache_size_mb=max_cache_size_mb
        )
        
        self.rate_limit_manager = RateLimitManager(
            config_file=rate_limit_config_file
        )
        
        # Data acquisition functions for different services
        self.data_acquirers: Dict[ServiceType, Callable] = {}
        
        logger.info("Integrated cache manager initialized")
    
    def register_data_acquirer(self, service_type: ServiceType, 
                             acquirer_func: Callable) -> None:
        """
        Register a data acquisition function for a service type.
        
        Args:
            service_type: Type of service
            acquirer_func: Async function to acquire data from the service
        """
        self.data_acquirers[service_type] = acquirer_func
        logger.info(f"Registered data acquirer for {service_type.value}")
    
    async def get_geographic_data(self, bounding_box: BoundingBox, 
                                level: CacheLevel,
                                service_type: ServiceType = ServiceType.OPENSTREETMAP,
                                force_refresh: bool = False,
                                additional_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get geographic data with automatic caching and rate limiting.
        
        Args:
            bounding_box: Geographic region to retrieve
            level: Cache level for the data
            service_type: Service to use for data acquisition
            force_refresh: Whether to bypass cache and fetch fresh data
            additional_params: Additional parameters for cache key generation
            
        Returns:
            Geographic data for the specified region
        """
        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_data = self.cache_manager.get_cached_data(
                bounding_box, level, additional_params
            )
            if cached_data:
                logger.debug(f"Cache hit for {level.value} data in region {bounding_box.to_dict()}")
                return cached_data
        
        # Need to acquire data from external service
        if service_type not in self.data_acquirers:
            raise ValueError(f"No data acquirer registered for {service_type.value}")
        
        logger.info(f"Acquiring {level.value} data from {service_type.value} "
                   f"for region {bounding_box.to_dict()}")
        
        # Use rate-limited request
        data = await self.rate_limit_manager.make_request(
            service_type,
            self.data_acquirers[service_type],
            bounding_box,
            level,
            additional_params or {}
        )
        
        # Store in cache
        cache_key = self.cache_manager.store_data(
            bounding_box, level, data, additional_params
        )
        
        logger.info(f"Cached {level.value} data with key {cache_key}")
        return data
    
    async def prepare_route_data(self, waypoints: list, 
                               config: RouteBufferConfig,
                               progress_callback: Optional[Callable[[str, float], None]] = None) -> Dict[str, Any]:
        """
        Prepare all necessary geographic data for a route.
        
        Args:
            waypoints: List of waypoint dictionaries with 'latitude' and 'longitude' keys
            config: Buffer configuration
            progress_callback: Optional callback for progress updates
            
        Returns:
            Summary of data preparation results
        """
        logger.info(f"Preparing geographic data for route with {len(waypoints)} waypoints")
        
        # Calculate required data regions
        required_regions = self.cache_manager.get_required_data_regions(waypoints, config)
        
        total_regions = sum(len(regions) for regions in required_regions.values())
        processed_regions = 0
        
        results = {
            "route_bounds": self.cache_manager.calculate_route_buffer(waypoints, config).to_dict(),
            "required_regions": {level.value: len(regions) for level, regions in required_regions.items()},
            "acquired_data": {},
            "errors": []
        }
        
        # Process each cache level
        for level, regions in required_regions.items():
            level_results = []
            
            for region in regions:
                try:
                    if progress_callback:
                        progress = processed_regions / total_regions if total_regions > 0 else 1.0
                        progress_callback(f"Acquiring {level.value} data", progress)
                    
                    # Determine appropriate service type based on level
                    service_type = self._get_service_type_for_level(level)
                    
                    # Acquire data
                    data = await self.get_geographic_data(
                        region, level, service_type
                    )
                    
                    level_results.append({
                        "region": region.to_dict(),
                        "data_size": len(str(data)),  # Rough size estimate
                        "success": True
                    })
                    
                except Exception as e:
                    error_msg = f"Failed to acquire {level.value} data for region {region.to_dict()}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
                    
                    level_results.append({
                        "region": region.to_dict(),
                        "error": str(e),
                        "success": False
                    })
                
                processed_regions += 1
            
            results["acquired_data"][level.value] = level_results
        
        if progress_callback:
            progress_callback("Data preparation complete", 1.0)
        
        logger.info(f"Route data preparation complete. "
                   f"Processed {processed_regions} regions with {len(results['errors'])} errors")
        
        return results
    
    def get_cache_coverage_report(self, waypoints: list, 
                                config: RouteBufferConfig) -> Dict[str, Any]:
        """
        Generate a report on cache coverage for a route.
        
        Args:
            waypoints: List of waypoint dictionaries with 'latitude' and 'longitude' keys
            config: Buffer configuration
            
        Returns:
            Coverage report with statistics and recommendations
        """
        route_bounds = self.cache_manager.calculate_route_buffer(waypoints, config)
        required_regions = self.cache_manager.get_required_data_regions(waypoints, config)
        
        coverage_report = {
            "route_bounds": route_bounds.to_dict(),
            "total_required_regions": sum(len(regions) for regions in required_regions.values()),
            "coverage_by_level": {},
            "estimated_download_time": 0.0,
            "recommendations": []
        }
        
        total_missing_regions = 0
        
        for level, regions in required_regions.items():
            missing_regions = len(regions)
            total_regions_for_level = len(regions) if regions else 1
            
            coverage_percentage = ((total_regions_for_level - missing_regions) / 
                                 total_regions_for_level * 100)
            
            coverage_report["coverage_by_level"][level.value] = {
                "total_regions": total_regions_for_level,
                "missing_regions": missing_regions,
                "coverage_percentage": coverage_percentage
            }
            
            total_missing_regions += missing_regions
        
        # Estimate download time based on rate limits and missing regions
        if total_missing_regions > 0:
            # Rough estimate: 2 seconds per region (including rate limiting)
            coverage_report["estimated_download_time"] = total_missing_regions * 2.0
            
            coverage_report["recommendations"].append(
                f"Need to download data for {total_missing_regions} regions. "
                f"Estimated time: {coverage_report['estimated_download_time'] / 60:.1f} minutes"
            )
        else:
            coverage_report["recommendations"].append(
                "All required geographic data is already cached"
            )
        
        return coverage_report
    
    def cleanup_and_optimize(self) -> Dict[str, Any]:
        """
        Perform cache cleanup and optimization.
        
        Returns:
            Summary of cleanup operations
        """
        logger.info("Starting cache cleanup and optimization")
        
        # Clean up expired entries
        expired_count = self.cache_manager.cleanup_expired_entries()
        
        # Get statistics before and after
        stats = self.get_comprehensive_statistics()
        
        cleanup_summary = {
            "expired_entries_removed": expired_count,
            "cache_statistics": stats,
            "recommendations": []
        }
        
        # Add recommendations based on statistics
        cache_stats = stats["cache_statistics"]
        if cache_stats["utilization"] > 0.9:
            cleanup_summary["recommendations"].append(
                "Cache utilization is high (>90%). Consider increasing cache size."
            )
        
        rate_stats = stats["rate_limiting_statistics"]
        for service, service_stats in rate_stats.items():
            if service_stats["recent_failure_rate"] > 20:
                cleanup_summary["recommendations"].append(
                    f"High failure rate for {service} ({service_stats['recent_failure_rate']:.1f}%). "
                    "Consider reducing request rate."
                )
        
        logger.info(f"Cache cleanup complete. Removed {expired_count} expired entries")
        return cleanup_summary
    
    def get_comprehensive_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics for both caching and rate limiting.
        
        Returns:
            Combined statistics from cache manager and rate limiter
        """
        return {
            "cache_statistics": self.cache_manager.get_cache_statistics(),
            "rate_limiting_statistics": self.rate_limit_manager.get_all_statistics(),
            "timestamp": datetime.now().isoformat()
        }
    
    def _get_service_type_for_level(self, level: CacheLevel) -> ServiceType:
        """
        Determine the appropriate service type for a cache level.
        
        Args:
            level: Cache level
            
        Returns:
            Appropriate service type
        """
        # Map cache levels to service types based on data requirements
        level_service_map = {
            CacheLevel.COUNTRY: ServiceType.OPENSTREETMAP,
            CacheLevel.STATE: ServiceType.OPENSTREETMAP,
            CacheLevel.REGION: ServiceType.OPENSTREETMAP,
            CacheLevel.CITY: ServiceType.OPENSTREETMAP
        }
        
        return level_service_map.get(level, ServiceType.OPENSTREETMAP)