import os
import socket
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def available_port(start_port: int = 8000, max_tries: int = 20) -> int:
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found between {start_port} and {start_port + max_tries - 1}")


def main() -> None:
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    configured_port = int(os.getenv("PORT", "8000"))
    port = configured_port if configured_port != 8000 else available_port(8000)
    reload_enabled = os.getenv("RELOAD", "false").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
