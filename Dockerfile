# Use a lightweight Python base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies
# tesseract-ocr is required for the project
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install the package in editable mode with dev dependencies
RUN pip install -e ".[dev]"

# Expose Streamlit port
EXPOSE 8501

# Default command: run the CLI help to show usage
CMD ["paystub-analyze", "--help"]
