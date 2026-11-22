FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build
FROM python:3.11-slim
WORKDIR /app
COPY requirements.demo.txt ./
RUN pip install --no-cache-dir -r requirements.demo.txt
COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN useradd --create-home medscout
USER medscout
ENV PORT=8000
CMD ["sh", "-c", "exec uvicorn backend.api.free_demo:app --host 0.0.0.0 --port ${PORT:-8000}"]
