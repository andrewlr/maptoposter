"""
API rate limiting for external service requests.

This module implements rate limiting functionality to ensure respectful
usage of external APIs like OpenStreetMap and geocoding services.
"""

import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass, field
from enum import Enum
import logging
from threading import Lock
import json
from pathlib import Path


logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Types of external services that require rate limiting."""
    OPENSTREETMAP = "openstreetmap"
    NOMINATIM = "nominatim"
    ROUTING = "routing"
    GEOCODING = "geocoding"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting a specific service."""
    requests_per_second: float
    requests_per_minute: int
    requests_per_hour: int
    burst_limit: int
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 300.0  # 5 minutes
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60  # seconds
    
    def __post_init__(self):
        """Validate rate limit configuration."""
        if self.requests_per_second <= 0:
            raise ValueError("Requests per second must be positive")
        if self.requests_per_minute <= 0:
            raise ValueError("Requests per minute must be positive")
        if self.requests_per_hour <= 0:
            raise ValueError("Requests per hour must be positive")
        if self.burst_limit <= 0:
            raise ValueError("Burst limit must be positive")
        if self.backoff_multiplier <= 1.0:
            raise ValueError("Backoff multiplier must be greater than 1.0")
        if self.max_backoff_seconds <= 0:
            raise ValueError("Max backoff seconds must be positive")


@dataclass
class RequestRecord:
    """Record of a single API request."""
    timestamp: datetime
    success: bool
    response_time: float
    error_message: Optional[str] = None


@dataclass
class ServiceStats:
    """Statistics for a rate-limited service."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited_requests: int = 0
    circuit_breaker_trips: int = 0
    total_wait_time: float = 0.0
    average_response_time: float = 0.0
    recent_requests: List[RequestRecord] = field(default_factory=list)
    
    def add_request(self, record: RequestRecord) -> None:
        """Add a request record and update statistics."""
        self.total_requests += 1
        
        if record.success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        # Update average response time
        if self.total_requests == 1:
            self.average_response_time = record.response_time
        else:
            self.average_response_time = (
                (self.average_response_time * (self.total_requests - 1) + record.response_time) 
                / self.total_requests
            )
        
        # Keep only recent requests (last 100)
        self.recent_requests.append(record)
        if len(self.recent_requests) > 100:
            self.recent_requests.pop(0)
    
    def get_success_rate(self) -> float:
        """Get the success rate as a percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    def get_recent_failure_rate(self, minutes: int = 5) -> float:
        """Get the failure rate for recent requests."""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_records = [r for r in self.recent_requests if r.timestamp >= cutoff_time]
        
        if not recent_records:
            return 0.0
        
        failed_count = sum(1 for r in recent_records if not r.success)
        return (failed_count / len(recent_records)) * 100


class CircuitBreaker:
    """Circuit breaker pattern implementation for API resilience."""
    
    def __init__(self, failure_threshold: int, timeout_seconds: int):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Time to wait before trying to close circuit
        """
        self.failure_threshold = failure_threshold
        self.timeout = timedelta(seconds=timeout_seconds)
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open
        self._lock = Lock()
    
    def can_proceed(self) -> bool:
        """Check if requests can proceed through the circuit breaker."""
        with self._lock:
            if self.state == "closed":
                return True
            elif self.state == "open":
                if self.last_failure_time and datetime.now() - self.last_failure_time > self.timeout:
                    self.state = "half-open"
                    return True
                return False
            else:  # half-open
                return True
    
    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self.failure_count = 0
            if self.state == "half-open":
                self.state = "closed"
    
    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


class TokenBucket:
    """Token bucket algorithm for rate limiting."""
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False otherwise
        """
        with self._lock:
            now = time.time()
            
            # Refill tokens based on elapsed time
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    def time_until_available(self, tokens: int = 1) -> float:
        """
        Calculate time until enough tokens are available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Time in seconds until tokens are available
        """
        with self._lock:
            if self.tokens >= tokens:
                return 0.0
            
            tokens_needed = tokens - self.tokens
            return tokens_needed / self.refill_rate


class RateLimiter:
    """
    Comprehensive rate limiter with multiple algorithms and circuit breaker.
    """
    
    def __init__(self, service_type: ServiceType, config: RateLimitConfig):
        """
        Initialize rate limiter for a specific service.
        
        Args:
            service_type: Type of service being rate limited
            config: Rate limiting configuration
        """
        self.service_type = service_type
        self.config = config
        
        # Token buckets for different time windows
        self.second_bucket = TokenBucket(
            capacity=max(1, int(config.requests_per_second)),
            refill_rate=config.requests_per_second
        )
        self.minute_bucket = TokenBucket(
            capacity=config.requests_per_minute,
            refill_rate=config.requests_per_minute / 60.0
        )
        self.hour_bucket = TokenBucket(
            capacity=config.requests_per_hour,
            refill_rate=config.requests_per_hour / 3600.0
        )
        self.burst_bucket = TokenBucket(
            capacity=config.burst_limit,
            refill_rate=config.requests_per_second
        )
        
        # Circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_threshold,
            timeout_seconds=config.circuit_breaker_timeout
        )
        
        # Statistics and state
        self.stats = ServiceStats()
        self.current_backoff = 1.0
        self.last_request_time = 0.0
        
        logger.info(f"Rate limiter initialized for {service_type.value}: "
                   f"{config.requests_per_second}/s, {config.requests_per_minute}/min, "
                   f"{config.requests_per_hour}/hour")
    
    async def acquire(self) -> None:
        """
        Acquire permission to make a request.
        
        This method will block until it's safe to proceed with the request.
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_proceed():
            wait_time = self.config.circuit_breaker_timeout
            logger.warning(f"Circuit breaker open for {self.service_type.value}, "
                          f"waiting {wait_time}s")
            await asyncio.sleep(wait_time)
            self.stats.total_wait_time += wait_time
        
        # Apply exponential backoff if needed
        if self.current_backoff > 1.0:
            backoff_time = min(self.current_backoff, self.config.max_backoff_seconds)
            logger.debug(f"Applying backoff for {self.service_type.value}: {backoff_time:.2f}s")
            await asyncio.sleep(backoff_time)
            self.stats.total_wait_time += backoff_time
        
        # Wait for token bucket availability
        max_wait = max(
            self.second_bucket.time_until_available(),
            self.minute_bucket.time_until_available(),
            self.hour_bucket.time_until_available(),
            self.burst_bucket.time_until_available()
        )
        
        if max_wait > 0:
            logger.debug(f"Rate limiting {self.service_type.value}: waiting {max_wait:.2f}s")
            await asyncio.sleep(max_wait)
            self.stats.total_wait_time += max_wait
        
        # Consume tokens from all buckets
        while not (self.second_bucket.consume() and 
                  self.minute_bucket.consume() and 
                  self.hour_bucket.consume() and 
                  self.burst_bucket.consume()):
            await asyncio.sleep(0.1)
            self.stats.total_wait_time += 0.1
        
        self.last_request_time = time.time()
    
    def record_success(self, response_time: float) -> None:
        """
        Record a successful request.
        
        Args:
            response_time: Time taken for the request in seconds
        """
        record = RequestRecord(
            timestamp=datetime.now(),
            success=True,
            response_time=response_time
        )
        
        self.stats.add_request(record)
        self.circuit_breaker.record_success()
        
        # Reset backoff on success
        self.current_backoff = 1.0
        
        logger.debug(f"Successful request to {self.service_type.value} "
                    f"in {response_time:.3f}s")
    
    def record_failure(self, error_message: str, is_rate_limit_error: bool = False) -> None:
        """
        Record a failed request.
        
        Args:
            error_message: Error message from the failed request
            is_rate_limit_error: Whether the failure was due to rate limiting
        """
        record = RequestRecord(
            timestamp=datetime.now(),
            success=False,
            response_time=0.0,
            error_message=error_message
        )
        
        self.stats.add_request(record)
        self.circuit_breaker.record_failure()
        
        if is_rate_limit_error:
            self.stats.rate_limited_requests += 1
            # Increase backoff for rate limit errors
            self.current_backoff = min(
                self.current_backoff * self.config.backoff_multiplier,
                self.config.max_backoff_seconds
            )
            logger.warning(f"Rate limited by {self.service_type.value}, "
                          f"backoff increased to {self.current_backoff:.2f}s")
        
        logger.warning(f"Failed request to {self.service_type.value}: {error_message}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "service_type": self.service_type.value,
            "total_requests": self.stats.total_requests,
            "successful_requests": self.stats.successful_requests,
            "failed_requests": self.stats.failed_requests,
            "rate_limited_requests": self.stats.rate_limited_requests,
            "success_rate": self.stats.get_success_rate(),
            "recent_failure_rate": self.stats.get_recent_failure_rate(),
            "circuit_breaker_trips": self.stats.circuit_breaker_trips,
            "circuit_breaker_state": self.circuit_breaker.state,
            "total_wait_time": self.stats.total_wait_time,
            "average_response_time": self.stats.average_response_time,
            "current_backoff": self.current_backoff
        }


class RateLimitManager:
    """
    Manager for multiple rate limiters across different services.
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize rate limit manager.
        
        Args:
            config_file: Optional path to configuration file
        """
        self.limiters: Dict[ServiceType, RateLimiter] = {}
        self.config_file = config_file
        
        # Load configuration
        if config_file and Path(config_file).exists():
            self._load_config(config_file)
        else:
            self._setup_default_configs()
    
    def get_limiter(self, service_type: ServiceType) -> RateLimiter:
        """Get rate limiter for a specific service type."""
        if service_type not in self.limiters:
            raise ValueError(f"No rate limiter configured for {service_type.value}")
        return self.limiters[service_type]
    
    async def make_request(self, service_type: ServiceType, 
                          request_func: Callable, *args, **kwargs) -> Any:
        """
        Make a rate-limited request to an external service.
        
        Args:
            service_type: Type of service being called
            request_func: Function to make the actual request
            *args, **kwargs: Arguments to pass to request_func
            
        Returns:
            Result from request_func
        """
        limiter = self.get_limiter(service_type)
        
        # Acquire permission to make request
        await limiter.acquire()
        
        # Make the request and record results
        start_time = time.time()
        try:
            result = await request_func(*args, **kwargs)
            response_time = time.time() - start_time
            limiter.record_success(response_time)
            return result
        
        except Exception as e:
            error_message = str(e)
            is_rate_limit = self._is_rate_limit_error(error_message)
            limiter.record_failure(error_message, is_rate_limit)
            raise
    
    def get_all_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all rate limiters."""
        return {
            service_type.value: limiter.get_statistics()
            for service_type, limiter in self.limiters.items()
        }
    
    def _setup_default_configs(self) -> None:
        """Setup default rate limiting configurations."""
        # OpenStreetMap API limits
        osm_config = RateLimitConfig(
            requests_per_second=1.0,
            requests_per_minute=60,
            requests_per_hour=3600,
            burst_limit=5
        )
        self.limiters[ServiceType.OPENSTREETMAP] = RateLimiter(ServiceType.OPENSTREETMAP, osm_config)
        
        # Nominatim geocoding limits (more restrictive)
        nominatim_config = RateLimitConfig(
            requests_per_second=0.5,  # 1 request per 2 seconds
            requests_per_minute=30,
            requests_per_hour=1800,
            burst_limit=3
        )
        self.limiters[ServiceType.NOMINATIM] = RateLimiter(ServiceType.NOMINATIM, nominatim_config)
        
        # Routing service limits
        routing_config = RateLimitConfig(
            requests_per_second=0.8,
            requests_per_minute=48,
            requests_per_hour=2880,
            burst_limit=4
        )
        self.limiters[ServiceType.ROUTING] = RateLimiter(ServiceType.ROUTING, routing_config)
        
        # Generic geocoding limits
        geocoding_config = RateLimitConfig(
            requests_per_second=0.5,
            requests_per_minute=30,
            requests_per_hour=1800,
            burst_limit=3
        )
        self.limiters[ServiceType.GEOCODING] = RateLimiter(ServiceType.GEOCODING, geocoding_config)
    
    def _load_config(self, config_file: str) -> None:
        """Load rate limiting configuration from file."""
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            for service_name, service_config in config_data.items():
                try:
                    service_type = ServiceType(service_name)
                    config = RateLimitConfig(**service_config)
                    self.limiters[service_type] = RateLimiter(service_type, config)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid configuration for {service_name}: {e}")
            
            logger.info(f"Loaded rate limiting configuration from {config_file}")
        
        except Exception as e:
            logger.warning(f"Failed to load rate limiting configuration: {e}")
            self._setup_default_configs()
    
    def _is_rate_limit_error(self, error_message: str) -> bool:
        """Check if an error message indicates rate limiting."""
        rate_limit_indicators = [
            "rate limit",
            "too many requests",
            "429",
            "quota exceeded",
            "throttled",
            "slow down"
        ]
        
        error_lower = error_message.lower()
        return any(indicator in error_lower for indicator in rate_limit_indicators)