# Dockerfile for the React frontend.
# We build the static files in a Node image, then serve them
# with Nginx for a small final image.

# --- Stage 1: build ---
FROM node:20-alpine AS builder
WORKDIR /app

# Install dependencies first (cached layer).
COPY package*.json ./
RUN npm install

# Copy the source code and build the production bundle.
COPY . .
RUN npm run build

# --- Stage 2: serve ---
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace the default Nginx config with one that proxies
# /api and /uploads to the backend container.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
