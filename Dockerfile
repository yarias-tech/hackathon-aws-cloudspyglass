# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ .
RUN npm run build


# Stage 2: Build backend dependencies
FROM python:3.12-slim AS backend-build

WORKDIR /app

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .


# Stage 3: Production image (Nginx + Uvicorn)
FROM python:3.12-slim AS production

# Install nginx and supervisor
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend dependencies
COPY --from=backend-build /install /usr/local

# Copy backend source
COPY backend/ ./backend/

# Copy frontend build to nginx html directory
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

# Copy assets (icons and logo)
COPY assets/ ./assets/

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/sites-enabled/default

# Copy supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create data directory
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
