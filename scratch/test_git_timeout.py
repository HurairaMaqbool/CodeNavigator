import git
import time
from pathlib import Path
import shutil

print("Testing git clone timeout...")
t0 = time.time()
try:
    git.Repo.clone_from(
        "https://github.com/psf/requests",
        "data/test_timeout_clone",
        depth=1,
        single_branch=True,
        env={"GIT_HTTP_CONNECT_TIMEOUT": "3"}
    )
except Exception as e:
    elapsed = time.time() - t0
    print(f"Git clone failed after {elapsed:.2f} seconds.")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {e}")

if Path("data/test_timeout_clone").exists():
    shutil.rmtree("data/test_timeout_clone")
