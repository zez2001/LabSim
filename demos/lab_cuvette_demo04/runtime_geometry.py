"""Reuse source-rack envelope and actual gripper input geometry methods.

These methods do not verify the original native seat void. The runtime keeps
native-seat penetration unavailable and the original-fit gate independently
blocked; it never substitutes a12.6mm analytic square for the retained tabs.
"""
from demos.lab_cuvette_demo03.runtime_geometry import fixture_measure,hand_clearance
