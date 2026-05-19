from cereal import log
import cereal.messaging as messaging


class LateralDataMarker:
  def build(self, CS, CC, model_data=None, lateral_plan=None):
    msg = messaging.new_message("lateralLearningInfo")
    info = msg.lateralLearningInfo
    lateral_offset = 0.0
    if lateral_plan is not None and len(lateral_plan.position.y) > 0:
      lateral_offset = float(lateral_plan.position.y[0])
    elif model_data is not None and len(model_data.position.y) > 0:
      lateral_offset = float(model_data.position.y[0])

    info.latActive = bool(CC.latActive)
    info.lateralOffset = lateral_offset
    info.vEgo = float(CS.vEgo)
    info.steeringPressed = bool(CS.steeringPressed)
    info.steeringTorqueDriver = float(CS.steeringTorque)
    info.lateralLearningFlag = self._flag(info)
    return msg

  @staticmethod
  def _flag(info):
    if info.vEgo < 5.0:
      return log.LateralLearningInfoData.Type.exclude
    if not info.latActive:
      return log.LateralLearningInfoData.Type.t5Manual
    if info.steeringPressed and abs(info.steeringTorqueDriver) >= 0.8:
      return log.LateralLearningInfoData.Type.t3StrongIntervention
    if info.steeringPressed and abs(info.steeringTorqueDriver) >= 0.2:
      return log.LateralLearningInfoData.Type.t4WeakIntervention
    if abs(info.lateralOffset) > 0.25:
      return log.LateralLearningInfoData.Type.t2Offset
    return log.LateralLearningInfoData.Type.t1Good
