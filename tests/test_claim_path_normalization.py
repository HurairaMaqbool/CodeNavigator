# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Path normalization for claim verification — Windows backslash parity."""
from __future__ import annotations

from app.agent.confidence import path_key, paths_match


def test_path_key_normalizes_windows_backslashes():
    assert path_key(r"src\requests\models.py") == "src/requests/models.py"
    assert path_key("src/requests/models.py") == "src/requests/models.py"


def test_paths_match_case_insensitive():
    assert paths_match("Src/Requests/Models.py", "src/requests/models.py") is True
    assert paths_match(r"src\requests\models.py", "src/requests/models.py") is True
