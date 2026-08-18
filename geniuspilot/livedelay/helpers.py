"""
Copyright (c) 2021-, Haibin Wen, geniuspilot, and a number of other contributors.

This file is part of geniuspilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params


def get_lat_delay(params: Params, stock_lat_delay: float) -> float:
  if params.get_bool("LagdToggle"):
    return float(params.get("LagdValueCache", return_default=True))

  return stock_lat_delay
