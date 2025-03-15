# Dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --progress-bar off --no-cache-dir -r requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "app.py","--server.address","0.0.0.0"]