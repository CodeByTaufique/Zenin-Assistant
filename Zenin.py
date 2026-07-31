"""
╔══════════════════════════════════════════════════════════════╗
║           Z E N I N  —  Personal AI Assistant               ║
║           Built for one. Loyal to one. You.                 ║
╚══════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import os
import sys
import signal
import logging
from pathlib import Path

from engine.core import ZeninCore
from engine.server import ZeninServer
from engine.config import Config

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s  —  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Zenin")


# ── Banner ─────────────────────────────────────────────────────────────────────
BANNER = r"""
 ______     ______     __   __     __     __   __    
/\___  \   /\  ___\   /\ "-.\ \   /\ \   /\ "-.\ \   
\/_/  /__  \ \  __\   \ \ \-.  \  \ \ \  \ \ \-.  \  
  /\_____\  \ \_____\  \ \_\\"\_\  \ \_\  \ \_\\"\_\ 
  \/_____/   \/_____/   \/_/ \/_/   \/_/   \/_/ \/_/ 

        Personal Intelligence System  v2.0
        Online. Operational. At your service.
"""


def print_banner():
    colors = {
        "cyan":  "\033[96m",
        "dim":   "\033[2m",
        "reset": "\033[0m",
    }
    print(f"{colors['cyan']}{BANNER}{colors['reset']}")


# ── Graceful shutdown ──────────────────────────────────────────────────────────
def install_signal_handlers(loop: asyncio.AbstractEventLoop, server: ZeninServer):
    def _shutdown():
        log.info("Shutdown signal received — standing down.")
        loop.create_task(server.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)


# ── Entry point ────────────────────────────────────────────────────────────────
async def main():
    print_banner()

    cfg  = Config.load()
    core = ZeninCore(cfg)
    srv  = ZeninServer(core, cfg)

    log.info("Initialising Zenin core systems …")
    await core.initialise()

    log.info(f"Starting web interface on http://localhost:{cfg.port}")
    loop = asyncio.get_running_loop()
    install_signal_handlers(loop, srv)

    await srv.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Zenin]  All systems offline. Goodbye.")
