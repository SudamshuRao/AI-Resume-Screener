#!/bin/bash
# HireIQ dev mode — backend in Docker, frontend with Vite hot reload
# Usage: ./dev.sh

set -e

echo "Starting backend services (db, chromadb, api-service, agent-service)..."
docker-compose up -d --build db chromadb api-service agent-service

echo ""
echo "Waiting for api-service to be ready..."
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
  sleep 2
done
echo "api-service is up."

echo ""
echo "Starting Vite dev server at http://localhost:3000 (hot reload enabled)"
echo "Press Ctrl+C to stop the frontend. Backend keeps running in Docker."
echo ""
cd services/frontend && npm run dev