FROM python:3.11-slim

WORKDIR /app

# Copy requirements from parent dir
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the frontend
COPY frontend /app/frontend

CMD ["streamlit", "run", "frontend/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
