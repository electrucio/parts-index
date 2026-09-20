"""Where things are. No module may hardcode an absolute path: ask here.

    REPO_ROOT        the checkout
    PUBLIC_DATA      REPO_ROOT/data            committed dataset
    data_root()      private, git-ignored working data: $PIDX_DATA_ROOT, else REPO_ROOT/private_uncommitted
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_DATA = REPO_ROOT / "data"


def data_root() -> Path:
    env = os.environ.get("PIDX_DATA_ROOT")
    return Path(env).expanduser() if env else REPO_ROOT / "private_uncommitted"
