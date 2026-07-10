import os
import re

read_text_re = re.compile(r'\.read_text\(\s*\)')

print("=== FINDING read_text() CALLS WITHOUT ENCODING IN TESTS ===")

tests_dir = 'tests'
for root, dirs, files in os.walk(tests_dir):
    for file in files:
        if file.endswith('.py') or file.endswith('.json'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            for idx, line in enumerate(lines):
                if read_text_re.search(line):
                    print(f"{filepath}:{idx+1}: {line.strip()}")
