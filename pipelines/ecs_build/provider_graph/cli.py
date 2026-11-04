# provider_graph/cli.py
from __future__ import annotations

from .config import from_env
from .pipeline import run

def main() -> None:
    cfg = from_env()
    print(f"RUN_ID={cfg.run_id} YEAR={cfg.year}")
    run(cfg, use_faiss=True)
    print("done")

if __name__ == "__main__":
    main()
