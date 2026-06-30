import importlib.util
import sys
from pathlib import Path

print("Python:", sys.executable)
venv_py = Path.cwd() / ".venv" / (
    "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
)
if ".venv" not in sys.executable.replace("\\", "/") and venv_py.exists():
    print(f"Hint: use project venv → {venv_py}")

mods = [
    "fastapi",
    "uvicorn",
    "streamlit",
    "chromadb",
    "sentence_transformers",
    "pydantic_settings",
]
for m in mods:
    print(f"{m}: {'OK' if importlib.util.find_spec(m) else 'MISSING'}")
