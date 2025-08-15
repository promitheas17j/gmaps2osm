FROM mcr.microsoft.com/playwright/python:v1.54.0-jammy AS base
WORKDIR /app/
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Comment for production:
CMD ["flask", "run"]
# Uncomment for production:
# CMD ["gunicorn", "-bind", "0.0.0.0:8000", "wsgi.app"]
