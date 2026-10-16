# Use official Python image
FROM python:3.12.3-slim

# Prevent Python from writing pyc files and buffering output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory inside container
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies (no separate pip upgrade to avoid PyPI timeout)
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project code
COPY . .

# Expose Django development server port
EXPOSE 8000

# Run Django dev server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]