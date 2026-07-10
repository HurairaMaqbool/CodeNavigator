import os
import re

except_re = re.compile(r'except\s*(?:Exception)?\s*:')
pass_continue_re = re.compile(r'^\s*(pass|continue)\b')

print("=== AUDITING BARE EXCEPT AND EXCEPT Exception: PASS/CONTINUE BLOCKS ===")

app_dir = 'app'
found_any = False
for root, dirs, files in os.walk(app_dir):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for idx, line in enumerate(lines):
                if except_re.search(line):
                    # Check if next line has pass or continue
                    next_idx = idx + 1
                    if next_idx < len(lines):
                        next_line = lines[next_idx]
                        if pass_continue_re.search(next_line):
                            rel_path = os.path.relpath(filepath, app_dir)
                            print(f"{filepath}:{idx+1}: {line.strip()} followed by {next_line.strip()}")
                            found_any = True

if not found_any:
    print("No bare except blocks swallowing errors found.")
