"""Pytest configuration / pytest 설정.

Ensures the project root is on ``sys.path`` so tests can import
``opsight.*`` without needing an editable install.
프로젝트 root를 ``sys.path``에 추가하여 editable install 없이도
``opsight.*`` import가 가능하게 한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
