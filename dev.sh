#!/usr/bin/env bash
set -euo pipefail

# CloudSpyglass — Development Environment Launcher
# Usage:
#   ./dev.sh          Start (or rebuild) the dev environment
#   ./dev.sh down     Stop and remove containers
#   ./dev.sh logs     Tail logs from all services
#   ./dev.sh restart  Restart all services
#   ./dev.sh rebuild  Force rebuild images and restart
#   ./dev.sh status   Show container status

COMPOSE_FILE="docker-compose.dev.yml"

print_banner() {
  echo ""
  echo "  ☁️  CloudSpyglass Dev Environment"
  echo "  ─────────────────────────────────"
  echo ""
}

print_urls() {
  echo ""
  echo "  ✅ Services running:"
  echo "     Frontend  → http://localhost:5173"
  echo "     Backend   → http://localhost:8000"
  echo "     Health    → http://localhost:8000/api/health"
  echo ""
  echo "  💡 Tips:"
  echo "     Run tests:  docker compose -f $COMPOSE_FILE exec backend pytest"
  echo "                 docker compose -f $COMPOSE_FILE exec frontend npm test"
  echo "     View logs:  ./dev.sh logs"
  echo "     Stop:       ./dev.sh down"
  echo ""
}

case "${1:-up}" in
  up|start)
    print_banner
    echo "  🔨 Building and starting containers..."
    docker compose -f "$COMPOSE_FILE" up -d --build
    print_urls
    ;;

  down|stop)
    print_banner
    echo "  🛑 Stopping containers..."
    docker compose -f "$COMPOSE_FILE" down
    echo "  Done."
    echo ""
    ;;

  logs)
    docker compose -f "$COMPOSE_FILE" logs -f
    ;;

  restart)
    print_banner
    echo "  🔄 Restarting containers..."
    docker compose -f "$COMPOSE_FILE" restart
    print_urls
    ;;

  rebuild)
    print_banner
    echo "  🔨 Rebuilding images from scratch..."
    docker compose -f "$COMPOSE_FILE" down
    docker compose -f "$COMPOSE_FILE" build --no-cache
    docker compose -f "$COMPOSE_FILE" up -d
    print_urls
    ;;

  status|ps)
    docker compose -f "$COMPOSE_FILE" ps
    ;;

  *)
    echo "Usage: ./dev.sh [up|down|logs|restart|rebuild|status]"
    exit 1
    ;;
esac
