import os
import re

print("=== PATCHING read_text() TO SPECIFY UTF-8 ENCODING IN TESTS ===")

read_text_re = re.compile(r'\.read_text\(\s*\)')
tests_dir = 'tests'

patched_count = 0

for root, dirs, files in os.walk(tests_dir):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if '.read_text()' in content:
                new_content = content.replace('.read_text()', '.read_text(encoding="utf-8")')
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Patched: {filepath}")
                patched_count += 1

print(f"Successfully patched {patched_count} files.")
