#pragma once

#include <string>

#include "common/params.h"
#include "selfdrive/pandad/panda.h"

void pandad_main_thread(std::string serial);

// This fork is deployed on C3/DOS hardware. Keep the native DOS Panda in the
// firmware contract instead of treating it as an unsupported legacy board:
// the Python wrapper flashes the checkout-local F4 image and the C++ process
// independently verifies the same signature before it starts CAN I/O.
static const std::vector<cereal::PandaState::PandaType> SUPPORTED_PANDA_TYPES = {
  cereal::PandaState::PandaType::DOS,
  cereal::PandaState::PandaType::RED_PANDA,
  cereal::PandaState::PandaType::TRES,
  cereal::PandaState::PandaType::CUATRO,
};


class PandaSafety {
public:
  PandaSafety(Panda *panda) : panda_(panda) {}
  void configureSafetyMode(bool is_onroad);
  bool getOffroadMode();

private:
  void updateMultiplexingMode();
  std::vector<std::string> fetchCarParams();
  void setSafetyMode(const std::vector<std::string> &params_string);

  bool initialized_ = false;
  bool log_once_ = false;
  bool safety_configured_ = false;
  bool prev_obd_multiplexing_ = false;
  Panda *panda_;
  Params params_;
};
