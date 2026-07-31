"""
engine/server.py
────────────────
Zenin's web server — serves the HUD frontend and the REST/SSE API.

Endpoints
─────────
GET  /                      → frontend HTML shell
GET  /api/status            → system status JSON
GET  /api/history           → conversation history JSON
POST /api/chat              → { "message": "..." }  → SSE stream
POST /api/clear             → clear conversation
POST /api/pin               → { "fact": "..." }      → pin a long-term fact
GET  /api/notes             → list note titles
POST /api/notes             → { "title": "...", "content": "..." }
DELETE /api/notes/<title>   → delete a note
GET  /assets/<path>         → static files
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("Zenin.Server")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


class ZeninServer:
    def __init__(self, core, cfg):
        self.core = core
        self.cfg  = cfg
        self._runner = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self):
        try:
            from aiohttp import web
            await self._start_aiohttp(web)
        except ImportError:
            log.info("aiohttp not found — falling back to built-in http.server")
            await self._start_builtin()

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    # ── aiohttp backend ────────────────────────────────────────────────────────

    async def _start_aiohttp(self, web):
        app = web.Application()
        app.router.add_get ("/",                    self._handle_index)
        app.router.add_get ("/api/status",          self._handle_status)
        app.router.add_get ("/api/history",         self._handle_history)
        app.router.add_post("/api/chat",            self._handle_chat)
        app.router.add_post("/api/clear",           self._handle_clear)
        app.router.add_post("/api/pin",             self._handle_pin)
        app.router.add_get ("/api/notes",           self._handle_notes_list)
        app.router.add_post("/api/notes",           self._handle_notes_create)
        app.router.add_delete("/api/notes/{title}", self._handle_notes_delete)
        app.router.add_static("/assets", FRONTEND_DIR / "assets", show_index=False)

        runner = web.AppRunner(app)
        await runner.setup()
        self._runner = runner

        site = web.TCPSite(runner, self.cfg.host, self.cfg.port)
        await site.start()

        log.info(
            f"✦  Zenin HUD active at  http://{self.cfg.host}:{self.cfg.port}"
        )

        # Keep running forever
        await asyncio.Event().wait()

    # ── Route handlers ─────────────────────────────────────────────────────────

    async def _handle_index(self, request):
        from aiohttp import web
        html_path = FRONTEND_DIR / "index.html"
        if html_path.exists():
            return web.FileResponse(html_path)
        return web.Response(text="<h1>Zenin — frontend not found</h1>", content_type="text/html")

    async def _handle_status(self, request):
        from aiohttp import web
        return web.json_response(self.core.get_status())

    async def _handle_history(self, request):
        from aiohttp import web
        return web.json_response(self.core.get_history())

    async def _handle_chat(self, request):
        from aiohttp import web, web_response

        body = await request.json()
        message = body.get("message", "").strip()
        if not message:
            return web.json_response({"error": "Empty message"}, status=400)

        # Server-Sent Events response
        resp = web.StreamResponse(
            status=200,
            headers={
                "Content-Type":  "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            },
        )
        await resp.prepare(request)

        try:
            async for chunk in self.core.chat(message):
                data = json.dumps({"token": chunk})
                await resp.write(f"data: {data}\n\n".encode())
        except Exception as exc:
            log.exception("Chat streaming error")
            err = json.dumps({"token": f"\n⚠ Error: {exc}"})
            await resp.write(f"data: {err}\n\n".encode())
        finally:
            await resp.write(b"data: [DONE]\n\n")

        return resp

    async def _handle_clear(self, request):
        from aiohttp import web
        self.core.clear_conversation()
        return web.json_response({"ok": True})

    async def _handle_pin(self, request):
        from aiohttp import web
        body = await request.json()
        fact = body.get("fact", "").strip()
        if not fact:
            return web.json_response({"error": "Empty fact"}, status=400)
        self.core.pin_fact(fact)
        return web.json_response({"ok": True})

    async def _handle_notes_list(self, request):
        from aiohttp import web
        return web.json_response({"notes": self.core.tools.list_note_titles()})

    async def _handle_notes_create(self, request):
        from aiohttp import web
        body  = await request.json()
        title = body.get("title", "").strip()
        content = body.get("content", "").strip()
        if not title or not content:
            return web.json_response({"error": "title and content required"}, status=400)
        nid = self.core.tools.save_note(title, content)
        return web.json_response({"id": nid})

    async def _handle_notes_delete(self, request):
        from aiohttp import web
        title = request.match_info["title"]
        ok    = self.core.tools.delete_note(title)
        return web.json_response({"ok": ok})

    # ── Fallback: built-in HTTP server ─────────────────────────────────────────

    async def _start_builtin(self):
        """
        Minimal fallback using Python's built-in http.server.
        Only serves static files — no SSE streaming.
        """
        import http.server
        import threading

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=str(FRONTEND_DIR), **kw)
            def log_message(self, *_): pass

        srv = http.server.HTTPServer((self.cfg.host, self.cfg.port), Handler)
        log.info(
            f"✦  Zenin static server at  http://{self.cfg.host}:{self.cfg.port}  "
            f"(install aiohttp for full functionality)"
        )
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        await asyncio.Event().wait()
