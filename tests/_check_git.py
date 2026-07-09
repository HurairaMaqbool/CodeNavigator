# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

import os
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

import git
print(git.__version__)
print("gitpython OK")
