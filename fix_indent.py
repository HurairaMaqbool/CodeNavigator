# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

import re

for filename in ['tests/test_module_6a.py', 'tests/test_module_6b.py', 'tests/test_module_10.py', 'tests/test_semantic_cache.py', 'tests/test_api_endpoints.py', 'tests/test_module_12.py', 'tests/test_module_13.py', 'tests/test_module_14.py', 'tests/test_module_15.py', 'tests/test_module_2.py', 'tests/test_module_8.py', 'tests/test_module_9a.py']:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            
        content = re.sub(r'(if .*?(?:CHROMA_AVAILABLE|ST_AVAILABLE|BM25_AVAILABLE|chromadb|sentence_transformers|rank_bm25).*?:\n)(\s*)(\S)', r'\1\2pass\n\2\3', content)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
    except FileNotFoundError:
        pass
