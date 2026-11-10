# Ballava in a container: one command builds everything and runs it the same way on any computer or server.
#   docker compose up --build        then open http://localhost:8000

# ---- Step 1: build the phone screens (React) with Node.js. Only used while building.
FROM node:22-alpine AS screens
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY build.mjs ./
COPY public ./public
COPY src ./src
RUN npm run build

# ---- Step 2: the Python app that actually runs.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=0 DATA_DIR=/data
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY manage.py ./
COPY config ./config
COPY kitchen ./kitchen
COPY --from=screens /build/dist ./dist
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput -v0

# Run as a normal user, not root. Family data lives in /data (a Docker volume), so it survives updates.
RUN useradd --create-home ballava && mkdir -p /data && chown ballava /data
USER ballava
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=4)"

# Update the database tables, then start the production web server.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 2 --threads 4 --access-logfile -"]
