FROM python:3.11-slim

WORKDIR /app

# Install git for repo cloning
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy requirements from parent dir (requires context to be the project root)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the actual app
COPY app /app/app
# Copy tests for the eval suite
COPY tests /app/tests

# Uvicorn expects module.path:app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
