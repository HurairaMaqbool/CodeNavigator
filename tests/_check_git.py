import os
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

import git
print(git.__version__)
print("gitpython OK")
