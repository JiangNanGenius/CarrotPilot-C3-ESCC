import pytest

from openpilot.selfdrive.ui.sunnypilot.onroad.curve_status import curve_status


@pytest.mark.parametrize('change,expected', [
  ({}, ('待命', 'idle', False)),
  ({'fresh': False, 'active': True, 'selected': True}, ('数据失效', 'unknown', False)),
  ({'enabled': False}, ('未启用', 'idle', False)),
  ({'approaching': True}, ('预判弯道', 'preview', False)),
  ({'active': True}, ('弯道计算', 'preview', False)),
  ({'active': True, 'selected': True}, ('限速 32', 'active', True)),
  ({'active': True, 'selected': True, 'override': True}, ('驾驶员接管', 'idle', False)),
  ({'active': True, 'selected': True, 'target': float('nan')}, ('弯道计算', 'preview', False)),
])
def test_truthful_curve_status(change, expected):
  args = dict(fresh=True, enabled=True, active=False, approaching=False, override=False, selected=False, target=32.)
  assert curve_status(**(args | change)) == expected
