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

# nginx:alpine runs envsubst on files in /etc/nginx/templates at startup,
# writing the result to /etc/nginx/conf.d/. ${BACKEND_URL} is substituted
# from the environment.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Compose BACKEND_URL from BACKEND_HOSTPORT before nginx's template
# expansion runs. nginx:alpine sources any /docker-entrypoint.d/*.envsh
# in the entrypoint shell (so exports survive); plain .sh files run in
# a subshell and their exports would be lost. The 20-envsubst-on-templates
# step that performs the substitution sorts after our 10-* prefix.
RUN printf '#!/bin/sh\nif [ -n "$BACKEND_HOSTPORT" ]; then\n  export BACKEND_URL="http://$BACKEND_HOSTPORT"\nfi\nexport BACKEND_URL="${BACKEND_URL:-http://backend:8000}"\n' \
    > /docker-entrypoint.d/10-derive-backend-url.envsh \
    && chmod +x /docker-entrypoint.d/10-derive-backend-url.envsh

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
