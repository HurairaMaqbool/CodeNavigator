import os
for root, dirs, files in os.walk(r"D:\github project\codenavigator\app"):
    for file in files:
        if file.endswith(".py"):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                try:
                    for i, line in enumerate(f):
                        if '.items()' in line:
                            print(f"{os.path.join(root, file)}:{i+1}:{line.strip()}")
                except Exception as e:
                    pass
