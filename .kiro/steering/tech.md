# CloudSpyglass — Tech Stack & Build

## Backend

- **Language**: Python 3.12+
- **Framework**: FastAPI + Uvicorn
- **AWS SDK**: boto3
- **Validation**: Pydantic v2
- **Testing**: pytest, pytest-asyncio, Hypothesis (property-based testing), moto (AWS mocking), httpx (API testing)
- **Linting**: ruff

## Frontend

- **Language**: TypeScript 6
- **Framework**: React 19, React Router 7
- **Bundler**: Vite 8
- **Diagram library**: @xyflow/react 12 (React Flow) with dagre for auto-layout
- **Export**: jspdf + html2canvas
- **Testing**: Vitest, @testing-library/react, fast-check (property-based testing), MSW (API mocking)
- **Linting**: oxlint

## Infrastructure

- **IaC**: Terraform (AWS provider ~5.0)
- **Deployment target**: AWS ECS Fargate behind an ALB
- **Container registry**: Amazon ECR
- **Production image**: Multi-stage Docker (Node 22 build → Python 3.12-slim + Nginx + supervisord)
- **Dev environment**: Docker Compose with hot-reload volumes

## Common Commands

All commands run inside Docker containers per the docker-environment steering rule.

| Action | Command |
|--------|---------|
| Start dev environment | `docker compose -f docker-compose.dev.yml up -d` |
| Rebuild after dep change | `docker compose -f docker-compose.dev.yml up -d --build` |
| Backend tests | `docker compose -f docker-compose.dev.yml exec backend pytest` |
| Backend lint | `docker compose -f docker-compose.dev.yml exec backend ruff check .` |
| Frontend tests | `docker compose -f docker-compose.dev.yml exec frontend npm test` |
| Frontend build | `docker compose -f docker-compose.dev.yml exec frontend npm run build` |
| Frontend lint | `docker compose -f docker-compose.dev.yml exec frontend npm run lint` |
| Production build | `docker build -t cloudspyglass .` |
| Production run | `docker compose up` (serves on :8080) |
| Terraform plan | `cd infra && terraform plan` |

## Key Conventions

- Backend API routes are prefixed with `/api/`.
- Frontend proxies `/api` requests to the backend (Vite dev proxy or Nginx in production).
- Property-based tests (Hypothesis / fast-check) are preferred for validating correctness invariants.
- Pydantic models live in `backend/models/` and TypeScript types in `frontend/src/types/`.
