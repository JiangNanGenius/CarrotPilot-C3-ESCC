from types import SimpleNamespace

import numpy as np
import pytest
from cereal import messaging
from openpilot.selfdrive.ui.soundd import Soundd, AudibleAlert, AudibleAlertSP


@pytest.mark.parametrize('alert', [AudibleAlert.warningImmediate, AudibleAlert.warningSoft, AudibleAlert.refuse,
                                 AudibleAlert.disengage, AudibleAlert.prompt])
def test_chime_never_replaces_existing_alert(alert):
  runner, sm = fixture(alert)
  Soundd.update_traffic_cue(runner, sm)
  assert runner.played == []


def fixture(alert=AudibleAlert.none, cue='starting'):
  from time import monotonic
  services = ('longitudinalPlan', 'carState', 'carControl', 'selfdriveState')
  class Messages(dict):
    pass
  sm = Messages({s: getattr(messaging.new_message(s), s) for s in services})
  sm.alive = sm.valid = dict.fromkeys(services, True)
  sm.recv_time = dict.fromkeys(services, monotonic())
  runner = SimpleNamespace(_frame=1, traffic_cues_enabled=True, enabled=False, current_alert=alert, played=[])
  runner.traffic_cues = SimpleNamespace(update=lambda *a, **kw: cue)
  runner.update_alert = runner.played.append
  return runner, sm


@pytest.mark.parametrize('cue,sound', [('starting', AudibleAlertSP.promptSingleHigh), ('detected', AudibleAlertSP.promptSingleLow)])
def test_chime_uses_one_shot_existing_asset(cue, sound):
  runner, sm = fixture(cue=cue)
  Soundd.update_traffic_cue(runner, sm)
  assert runner.played == [sound]


def test_new_warning_also_suppresses_cue():
  runner, sm = fixture()
  sm['selfdriveState'].alertSound = AudibleAlert.warningImmediate
  Soundd.update_traffic_cue(runner, sm)
  assert runner.played == []


def test_explicit_courtesy_chime_only_bypasses_quiet_for_its_own_playback():
  runner = SimpleNamespace(current_alert=AudibleAlertSP.promptSingleHigh, courtesy_chime=True,
                           current_sound_frame=0, current_volume=1.0,
                           should_play_sound=lambda alert: False,
                           loaded_sounds={AudibleAlertSP.promptSingleHigh: np.ones(8)})
  assert np.any(Soundd.get_sound_data(runner, 4))
  runner.courtesy_chime = False
  assert not np.any(Soundd.get_sound_data(runner, 4))
