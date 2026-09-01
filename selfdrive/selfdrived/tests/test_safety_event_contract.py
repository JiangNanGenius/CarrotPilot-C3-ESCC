from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SELFDRIVED = ROOT / "selfdrive/selfdrived/selfdrived.py"


def test_critical_process_health_events_are_not_bypassed():
  source = SELFDRIVED.read_text()

  assert "pass#self.events.add" not in source
  for event in (
    "processNotRunning",
    "cameraMalfunction",
    "commIssue",
    "commIssueAvgFreq",
    "sensorDataInvalid",
    "noGps",
  ):
    assert f"self.events.add(EventName.{event})" in source


def test_invalid_advisory_envelopes_do_not_publish_stale_events():
  source = SELFDRIVED.read_text()

  assert "if service_data_available(self.sm, 'driverMonitoringState')" in source
  assert "if service_data_available(self.sm, 'longitudinalPlanSP')" in source
