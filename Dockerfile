# PARALLAX: one container serving the FastAPI science backend and the built web app.
# Build:  docker build -t parallax .
# Run:    docker run -p 8000:8000 parallax      -> http://localhost:8000
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ api/
COPY pipeline/ pipeline/
COPY validation/ validation/
COPY data/ data/
COPY docs/ docs/
COPY --from=web /web/dist web/dist
# Curated targets ship as processed products (frames, investigations, provenance). Native FITS cutouts are
# re-fetched from IRSA on demand and verified against their recorded SHA-256.
RUN mkdir -p .parallax-cache && useradd -m parallax && chown -R parallax /app
USER parallax
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
