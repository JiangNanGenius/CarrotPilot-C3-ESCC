"""Helpers for validating cross-rate message inputs by producer timestamps."""


NANOSECONDS_PER_SECOND = 1_000_000_000
_REFERENCE_TIME_CACHE_ATTR = "_producer_freshness_reference_times"


def inputs_fresh(sm, reference_service: str, max_age_seconds: dict[str, float]) -> bool:
  """Return whether a new reference packet and its dependencies are usable.

  ``SubMaster.freq_ok`` measures receive timing in the consumer process. On a
  loaded C3, a briefly delayed consumer can therefore reject producer streams
  which are current and publishing at the correct rate. Processes clocked by a
  specific input already know that a new reference packet arrived; compare the
  producer ``logMonoTime`` values instead and retain explicit packet validity.

  A stopped dependency still fails closed once its producer timestamp exceeds
  the service-specific age bound.
  """
  if not sm.updated[reference_service] or not sm.valid[reference_service]:
    return False

  reference_time = sm.logMonoTime[reference_service]
  if reference_time <= 0:
    return False

  # A faulty producer can keep transmitting valid-looking envelopes with a
  # frozen timestamp. ``updated`` alone only proves another packet arrived;
  # require producer time to advance as well. The cache lives on this
  # SubMaster instance, so independent processes and replay prefixes remain
  # isolated.
  reference_times = getattr(sm, _REFERENCE_TIME_CACHE_ATTR, None)
  if reference_times is None:
    reference_times = {}
    setattr(sm, _REFERENCE_TIME_CACHE_ATTR, reference_times)
  if reference_time <= reference_times.get(reference_service, 0):
    return False
  reference_times[reference_service] = reference_time

  for service, max_age in max_age_seconds.items():
    service_time = sm.logMonoTime[service]
    if (not sm.valid[service] or service_time <= 0 or
        abs(reference_time - service_time) > int(max_age * NANOSECONDS_PER_SECOND)):
      return False

  return True
