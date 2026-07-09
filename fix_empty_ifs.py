# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

import re

for filename in ['tests/test_module_6a.py', 'tests/test_module_6b.py', 'tests/test_module_9a.py']:
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    content = re.sub(r'if not (?:CHROMA_AVAILABLE|ST_AVAILABLE|BM25_AVAILABLE):\n\s+pass\n', '', content)
    content = re.sub(r'if \".*?\" not in sys\.modules:\n\s+pass\n', '', content)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
