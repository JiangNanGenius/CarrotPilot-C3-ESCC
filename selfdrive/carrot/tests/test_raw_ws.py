import asyncio

from openpilot.selfdrive.carrot.realtime.transports.camera_ws import CameraWsHub
from openpilot.selfdrive.carrot.realtime.transports.raw_ws import RawWsHub


class FakeSocket:
  def __init__(self):
    self.receive_calls = 0

  def receive(self, *, non_blocking):
    assert non_blocking
    self.receive_calls += 1
    return None


class FakeMessaging:
  def __init__(self):
    self.sub_sock_calls = []
    self.sockets = {}

  def sub_sock(self, service, *, conflate):
    self.sub_sock_calls.append((service, conflate))
    return self.sockets.setdefault(service, FakeSocket())

  def recv_one_or_none(self, sock):
    return None


class FakeWebSocket:
  async def close(self, *, code=None, message=None):
    pass


async def wait_until(predicate):
  for _ in range(100):
    if predicate():
      return
    await asyncio.sleep(0)
  raise AssertionError("condition was not reached")


def test_raw_socket_is_reused_after_idle_restart():
  async def run_test():
    messaging = FakeMessaging()
    hub = RawWsHub(messaging)
    hub.IDLE_SLEEP = 0
    hub.ACTIVE_POLL_SLEEP = 0
    hub.IDLE_STOP_SEC = 0

    for _ in range(50):
      existing_socket = messaging.sockets.get("carState")
      receive_count_before = existing_socket.receive_calls if existing_socket is not None else 0
      ws = FakeWebSocket()
      await hub.register("carState", ws)
      task = hub._tasks["carState"]
      await wait_until(lambda before=receive_count_before: (
        len(messaging.sub_sock_calls) == 1 and
        messaging.sockets["carState"].receive_calls > before
      ))
      await hub.unregister_client(ws)
      await asyncio.wait_for(task, timeout=1)

    assert messaging.sub_sock_calls == [("carState", True)]
    assert hub._sockets["carState"] is messaging.sockets["carState"]

    await hub.stop_all()
    assert hub._sockets == {}

  asyncio.run(run_test())


def test_camera_state_socket_is_reused_after_idle_restart():
  async def run_test():
    messaging = FakeMessaging()
    hub = CameraWsHub(messaging)
    hub.IDLE_STOP_SEC = 0

    first_ws = FakeWebSocket()
    hub.clients["road"].add(first_ws)
    await hub.ensure_camera_task("road")
    first_producer = hub._producer_tasks["road"]
    first_sender = hub._sender_tasks["road"]
    await wait_until(lambda: len(messaging.sub_sock_calls) == 1)

    hub.clients["road"].discard(first_ws)
    await asyncio.wait_for(first_producer, timeout=1)
    await asyncio.wait_for(first_sender, timeout=1)
    state_socket = hub._sockets["road"]["roadCameraState"]

    second_ws = FakeWebSocket()
    hub.clients["road"].add(second_ws)
    await hub.ensure_camera_task("road")
    await asyncio.sleep(0)

    assert messaging.sub_sock_calls == [("roadCameraState", True)]
    assert hub._sockets["road"]["roadCameraState"] is state_socket

    hub.clients["road"].discard(second_ws)
    await hub.stop_all()
    assert hub._sockets["road"] == {}

  asyncio.run(run_test())
