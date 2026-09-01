#!/usr/bin/env python3
import cereal.messaging as messaging
from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process
from openpilot.selfdrive.monitoring.helpers import DriverMonitoring


DM_RATE_CHECKED_SERVICES = ['liveCalibration', 'modelV2']
DM_AUX_INPUT_SERVICES = ['carState', 'selfdriveState', 'carControl']


def inputs_alive_and_valid(sm, services=DM_AUX_INPUT_SERVICES):
  """Check safety-relevant message health without rejecting rate jitter.

  dmonitoringd is polled by driverStateV2 and samples faster producers such as
  carState/carControl. Their measured receive rate can legitimately differ
  from the service declaration, so an aggregate frequency check can keep every
  output invalid even though current, valid messages are continuously present.
  Alive + message-valid remains fail closed for dead or explicitly-invalid
  producers.
  """
  return sm.all_alive(services) and sm.all_valid(services)


def dmonitoring_inputs_valid(sm) -> bool:
  return (sm.all_checks(['driverStateV2', *DM_RATE_CHECKED_SERVICES]) and
          inputs_alive_and_valid(sm))


def dmonitoringd_thread():
  config_realtime_process([0, 1, 2, 3], 5)

  params = Params()
  pm = messaging.PubMaster(['driverMonitoringState'])
  sm = messaging.SubMaster(['driverStateV2', 'liveCalibration', 'carState', 'selfdriveState', 'modelV2',
                            'carControl'], poll='driverStateV2')

  DM = DriverMonitoring(rhd_saved=params.get_bool("IsRhdDetected"), always_on=params.get_bool("AlwaysOnDM"))
  demo_mode=False

  # 20Hz <- dmonitoringmodeld
  while True:
    sm.update()
    if not sm.updated['driverStateV2']:
      # iterate when model has new output
      continue

    # Keep full frequency checks for same-rate model/calibration inputs. Faster
    # control and car streams are sampled at this slower loop rate, so require
    # them alive+valid without treating harmless scheduling jitter as failure.
    driver_state_valid = sm.all_checks(['driverStateV2'])
    valid = dmonitoring_inputs_valid(sm)
    packet_valid = driver_state_valid if demo_mode else valid

    if demo_mode and driver_state_valid:
      DM.run_step(sm, demo=demo_mode)
    elif valid:
      DM.run_step(sm, demo=demo_mode)
    elif driver_state_valid:
      # Preserve camera/RHD/face updates through an auxiliary-input outage,
      # but publish invalid and do not advance awareness safety events.
      car_state_valid = inputs_alive_and_valid(sm, ['carState'])
      engagement_valid = inputs_alive_and_valid(sm, ['selfdriveState', 'carControl'])
      CS = sm['carState']
      DM.update_driver_metadata_only(
        sm['driverStateV2'],
        car_speed=CS.vEgo if car_state_valid else 0.,
        op_engaged=(sm['selfdriveState'].enabled or sm['carControl'].latActive) if engagement_valid else False,
      )

    # publish
    dat = DM.get_state_packet(valid=packet_valid)
    pm.send('driverMonitoringState', dat)

    # load live always-on toggle
    if sm['driverStateV2'].frameId % 40 == 1:
      DM.always_on = params.get_bool("AlwaysOnDM")
      demo_mode = params.get_bool("IsDriverViewEnabled")

    # save rhd virtual toggle every 5 mins
    if (sm['driverStateV2'].frameId % 6000 == 0 and not demo_mode and
     DM.wheelpos.prob_offseter.filtered_stat.n > DM.settings._WHEELPOS_FILTER_MIN_COUNT and
     DM.wheel_on_right == (DM.wheelpos.prob_offseter.filtered_stat.M > DM.settings._WHEELPOS_THRESHOLD)):
      params.put_bool_nonblocking("IsRhdDetected", DM.wheel_on_right)

def main():
  dmonitoringd_thread()


if __name__ == '__main__':
  main()
