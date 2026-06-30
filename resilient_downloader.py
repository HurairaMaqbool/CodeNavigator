import urllib.request
import urllib.parse
import re
import sys
import os
import time
from html.parser import HTMLParser

class SimpleIndexParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attrs_dict = dict(attrs)
            if 'href' in attrs_dict:
                href = attrs_dict['href']
                filename = href.split('/')[-1].split('#')[0]
                self.urls[filename] = href

def get_wheel_url(package_name, pattern):
    url = f"https://mirrors.aliyun.com/pypi/simple/{package_name}/"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            parser = SimpleIndexParser()
            parser.feed(html)
            
            # Find the wheel matching the pattern
            # For torch, we want version 2.2.x or 2.3.x, NOT 2.10.x which might be nightly or future
            best_filename = None
            best_url = None
            for filename, href in parser.urls.items():
                if re.match(pattern, filename):
                    best_filename = filename
                    best_url = urllib.parse.urljoin(url, href)
                    # For torch, pick 2.2.1 if available
                    if "2.2.1" in filename:
                        break
            return best_url, best_filename
    except Exception as e:
        print(f"Failed to fetch {package_name}: {e}")
    return None, None

def download_file_with_resume(url, filename, max_retries=50):
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url)
            
            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
                req.add_header('Range', f'bytes={file_size}-')
                print(f"Resuming {filename} from byte {file_size}...")
                mode = 'ab'
            else:
                print(f"Starting new download for {filename}...")
                file_size = 0
                mode = 'wb'

            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = response.length
                print(f"Remaining bytes: {total_size}")
                
                with open(filename, mode) as f:
                    while True:
                        chunk = response.read(8192 * 4)
                        if not chunk:
                            break
                        f.write(chunk)
            
            print(f"Successfully downloaded {filename}!")
            return True
            
        except urllib.error.HTTPError as e:
            if e.code == 416: # Range Not Satisfiable
                print(f"{filename} already fully downloaded!")
                return True
            print(f"HTTP Error: {e.code}")
            time.sleep(5)
        except Exception as e:
            print(f"Network error: {e}")
            time.sleep(3)
            
    print(f"Failed to download {filename} after {max_retries} attempts.")
    return False

if __name__ == "__main__":
    # Patterns for the exact wheels pip was trying to download
    packages = [
        ("torch", r"torch-.*-cp312-cp312-win_amd64\.whl"),
        ("transformers", r"transformers-.*-py3-none-any\.whl"),
        ("ruff", r"ruff-.*-win_amd64\.whl"),
    ]
    
    for pkg, pattern in packages:
        print(f"Finding URL for {pkg}...")
        url, filename = get_wheel_url(pkg, pattern)
        if url:
            print(f"Found: {filename}")
            download_file_with_resume(url, filename)
        else:
            print(f"Could not find matching wheel for {pkg}")
