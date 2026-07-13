FROM python:3.12-slim

WORKDIR /app

# System deps for pandas/pyarrow wheels are prebuilt; keep image slim.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Seed on first boot is optional; start the API server.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
