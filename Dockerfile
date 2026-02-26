FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY run_api.py .

EXPOSE 8000

CMD ["python", "run_api.py"]
