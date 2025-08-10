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

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/main.py .
COPY src/database.py .

# Create static directory and copy frontend
RUN mkdir -p /app/static /app/uploads
COPY static/frontend.html ./static/
COPY static/logo.png ./static/

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]