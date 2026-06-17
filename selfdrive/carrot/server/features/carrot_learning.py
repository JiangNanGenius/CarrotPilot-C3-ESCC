from aiohttp import web

from ..services.carrot_learning import get_learning_state, handle_learning_action


async def api_carrot_learning(request: web.Request) -> web.Response:
  try:
    return web.json_response({"ok": True, **get_learning_state()}, headers={"Cache-Control": "no-store"})
  except Exception as e:
    return web.json_response({"ok": False, "error": str(e)}, status=500)


async def api_carrot_learning_action(request: web.Request) -> web.Response:
  try:
    body = await request.json()
  except Exception:
    body = {}
  action = str(body.get("action", "")).strip()
  if not action:
    return web.json_response({"ok": False, "error": "missing action"}, status=400)
  try:
    result = handle_learning_action(action)
    return web.json_response({"ok": True, **result, **get_learning_state()})
  except Exception as e:
    return web.json_response({"ok": False, "error": str(e)}, status=400)


def register(app: web.Application) -> None:
  app.router.add_get("/api/carrot_learning", api_carrot_learning)
  app.router.add_post("/api/carrot_learning", api_carrot_learning_action)
