FROM python:3.13-slim

# Add labels for GitHub Container Registry linking
LABEL org.opencontainers.image.source=https://github.com/bifr0est/rezeptviewer
LABEL org.opencontainers.image.description="Recipe Viewer Web Application"
LABEL org.opencontainers.image.licenses=MIT

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy application code and templates first
COPY app/ ./app/
COPY templates/ ./templates/
COPY static/ ./static/

# Copy pyproject.toml and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Create uploads directory
RUN mkdir -p /app/uploads

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]