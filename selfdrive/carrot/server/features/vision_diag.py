import asyncio

from aiohttp import web

from ..services.vision_diag import get_server_diagnostic_snapshot


async def api_vision_diag_server_snapshot(_request: web.Request) -> web.Response:
  snapshot = await asyncio.to_thread(get_server_diagnostic_snapshot)
  return web.json_response({"ok": True, "snapshot": snapshot})


def register(app: web.Application) -> None:
  app.router.add_get("/api/vision_diag/server_snapshot", api_vision_diag_server_snapshot)
