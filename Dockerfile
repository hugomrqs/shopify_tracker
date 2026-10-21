FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY crawler ./crawler
COPY normalize_categories.py ./
COPY taxonomy ./taxonomy

CMD ["python", "-m", "crawler.main"]
