# Single-stage Dockerfile tuned for slow networks + low Docker Desktop memory.
# - One FROM (no second Docker Hub pull / TLS timeout)
# - No gcc/g++ (all deps use manylinux wheels; saves ~400MB RAM during apt)
# - Heavy pip wheels in separate layers (retry one layer on IncompleteRead)
#
# Build ONE image, reuse for backend/worker:
#   docker compose build backend
#   docker compose up

FROM python:3.12-slim

# Digest pin: use local cache when Hub is flaky (update when upgrading base image)
# python:3.12-slim @sha256:6c4dd321d176d61ea848dc8c73a4f7dbae8f70e0ee48bb411ea2f045b599fa8e

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PIP_DEFAULT_TIMEOUT=600
ENV PIP_RETRIES=15
ENV PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip

# Layer 1: PyTorch CPU
RUN pip install --timeout=600 --retries=15 \
    torch==2.4.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Layer 2: scipy alone — if this fails, rerun: docker compose build app
RUN pip install --timeout=600 --retries=15 scipy==1.13.0

# Layer 3: other heavy wheels (NOT scipy 1.18 from resolver backtracking)
RUN pip install --timeout=600 --retries=15 \
    numpy==2.1.3 pandas==2.2.3 pyarrow==17.0.0 scikit-learn==1.5.2

# Layer 4: app deps (requirements-docker.txt — NOT full requirements.txt)
COPY requirements-docker.txt requirements-heavy.txt requirements-eval.txt ./
RUN pip install --timeout=600 --retries=15 -r requirements-docker.txt
RUN pip install --timeout=600 --retries=15 -r requirements-eval.txt

COPY . .

# Pre-download the default embedding model so first ingest does not block on HuggingFace.
ENV HF_HOME=/app/data/huggingface
RUN mkdir -p /app/data/huggingface && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8000

CMD ["gunicorn", "app.main:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120", "--graceful-timeout", "30"]
