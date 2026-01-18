"""
Route processing and calculation components for the Road Trip Animator.

This package contains modules for calculating routes between waypoints and managing
custom route overrides.
"""

from .processor import RouteProcessor
from .custom_routes import CustomRouteManager

__all__ = ['RouteProcessor', 'CustomRouteManager']