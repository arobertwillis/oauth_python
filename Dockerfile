# Use the official Python 3.14 Slim image based on Debian Trixie
FROM python:3.14-slim-trixie

# Set environment variables
# PYTHONDONTWRITEBYTECODE=1: Prevents Python from writing .pyc files to disk
# PYTHONUNBUFFERED=1: Ensures that Python output is logged to the terminal
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt /app/

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY app/ /app/app/

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
