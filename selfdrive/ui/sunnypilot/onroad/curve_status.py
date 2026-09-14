"""Display-only SCC states; these never alter controller thresholds."""
import math


def curve_status(*, fresh, enabled, active, approaching, override, selected, target):
  if not fresh:
    return '数据失效', 'unknown', False
  if not enabled:
    return '未启用', 'idle', False
  if override:
    return '驾驶员接管', 'idle', False
  if active and selected and math.isfinite(target) and 0 <= target <= 160:
    return f'限速 {target:.0f}', 'active', True
  if active:
    return '弯道计算', 'preview', False
  if approaching:
    return '预判弯道', 'preview', False
  return '待命', 'idle', False
