# Dockerfile for the FastAPI backend.
# We use the official slim Python image to keep the size small.
FROM python:3.11-slim

# Set the working folder inside the container.
WORKDIR /app

# Install system libraries that OpenCV / Pillow need.
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file first.
# Doing this in a separate step lets Docker cache the pip install
# layer when only the app code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code (including the weights folder).
COPY . .

# Make sure the uploads folder exists.
RUN mkdir -p uploads

# Tell Docker which port the app uses.
EXPOSE 8000

# Start the server. We use 0.0.0.0 so it is reachable
# from outside the container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
