# KachraCheck: one image, two commands (API on 8000, Streamlit UI on 8501).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so Docker can cache this layer between code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && pip install uvicorn streamlit

COPY . .

# Run as a normal user, not root. /feedback holds the UI's thumbs up/down file.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /feedback \
    && chown -R appuser:appuser /app /feedback
USER appuser

EXPOSE 8000 8501

# Default command = the API. docker-compose overrides it for the UI.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
