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

# Opt into nginx:alpine's 15-local-resolvers hook, which reads
# /etc/resolv.conf and exports NGINX_LOCAL_RESOLVERS for the template.
# Without this env var, the hook returns early and our resolver line
# stays unfilled — nginx then refuses to start.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

# Provide BACKEND_HOST and BACKEND_PORT to the nginx template before
# the envsubst step runs. We split BACKEND_HOSTPORT (set by Render
# via render.yaml) on the colon; if absent (e.g. docker-compose),
# fall back to the compose service name "backend:8000".
#
# nginx:alpine sources /docker-entrypoint.d/*.envsh in the entrypoint
# shell (so exports survive into envsubst and nginx); plain .sh files
# run in a subshell where the exports would be lost. The 20-envsubst
# step sorts after our 10-* prefix.
RUN printf '%s\n' \
    '#!/bin/sh' \
    ': "${BACKEND_HOSTPORT:=backend:8000}"' \
    'export BACKEND_HOST="${BACKEND_HOSTPORT%%:*}"' \
    'export BACKEND_PORT="${BACKEND_HOSTPORT##*:}"' \
    '# If hostport had no colon, ${...##*:} returns the host; default port to 8000.' \
    'if [ "$BACKEND_HOST" = "$BACKEND_PORT" ]; then export BACKEND_PORT=8000; fi' \
    > /docker-entrypoint.d/10-derive-backend-url.envsh \
    && chmod +x /docker-entrypoint.d/10-derive-backend-url.envsh

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
