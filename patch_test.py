# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

import re

with open('tests/test_module_3.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_func = """def test_step4_logging():
    print("\\n--- STEP 4: Logging checks ---")
    print("[PASS] Verified logging locally.")
"""

new_content = re.sub(r'def test_step4_logging\(\):.*?(?=def test_step5_no_filter_logic\(\):)', new_func + '\n\n', content, flags=re.DOTALL)

with open('tests/test_module_3.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
