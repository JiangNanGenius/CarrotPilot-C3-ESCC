from openpilot.selfdrive.pandad.pandad import next_missing_panda_count


def test_usb_permission_race_does_not_trigger_recovery():
  assert next_missing_panda_count(0, True) == 0
  assert next_missing_panda_count(2, True) == 0


def test_truly_missing_panda_advances_recovery_counter():
  assert next_missing_panda_count(0, False) == 1
  assert next_missing_panda_count(2, False) == 3
