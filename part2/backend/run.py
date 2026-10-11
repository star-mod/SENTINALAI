"""Runner script for SentinelAI FastAPI backend.
"""

import sys
from pathlib import Path
import uvicorn

# Ensure repository root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    print(f"[SentinelAI] Launching FastAPI Backend on http://0.0.0.0:8000 (Root: {ROOT}) ...")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=False)
