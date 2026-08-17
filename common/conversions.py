"""Unit conversion constants.

This base has no common/conversions.py; delegate to opendbc's Conversions so
carrot and other openpilot-style imports keep working.
"""
from opendbc.car.common.conversions import Conversions

__all__ = ["Conversions"]
