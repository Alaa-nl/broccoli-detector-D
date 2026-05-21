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
# writing the result to /etc/nginx/conf.d/. Vars in ${...} form are
# substituted from the environment.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Provide BACKEND_SCHEME, BACKEND_HOST, BACKEND_PORT to the nginx
# template before the envsubst step runs. Defaults match docker-compose
# (plain HTTP to the "backend" service); Render overrides via render.yaml
# with the public *.onrender.com URL.
#
# nginx:alpine sources /docker-entrypoint.d/*.envsh in the entrypoint
# shell (so exports survive into envsubst and nginx); plain .sh files
# run in a subshell where the exports would be lost. The 20-envsubst
# step sorts after our 10-* prefix.
RUN printf '%s\n' \
    '#!/bin/sh' \
    'export BACKEND_SCHEME="${BACKEND_SCHEME:-http}"' \
    'export BACKEND_HOST="${BACKEND_HOST:-backend}"' \
    'export BACKEND_PORT="${BACKEND_PORT:-8000}"' \
    'export DNS_RESOLVER="${DNS_RESOLVER:-1.1.1.1 1.0.0.1}"' \
    > /docker-entrypoint.d/10-derive-backend-url.envsh \
    && chmod +x /docker-entrypoint.d/10-derive-backend-url.envsh

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
