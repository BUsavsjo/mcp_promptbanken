FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 connect
COPY connect_service ./connect_service
USER connect
EXPOSE 8010
CMD ["python", "-m", "connect_service"]
