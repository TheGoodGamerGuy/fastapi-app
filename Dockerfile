# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app directory to the working directory
COPY ./app ./app

# # Create necessary directories and set permissions
# RUN mkdir -p /app/app/logs && \
#     touch /app/app/logs/application.log && \
#     chmod 777 /app/app/logs /app/app/logs/application.log

# Expose the application port
EXPOSE 7080

# Run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7080"]