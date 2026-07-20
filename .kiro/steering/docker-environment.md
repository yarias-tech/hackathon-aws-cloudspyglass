# Docker-Only Development Environment

All builds, tests, and application execution MUST run inside the Docker environment. Do NOT install or run anything directly on the host machine.

## Rules

- Never run `npm install`, `npm test`, `npm run build`, `pip install`, `pytest`, or any project command directly on the host.
- Always use the Docker Compose dev environment for all operations.
- The host machine should only have Docker installed — no Node.js, Python, or project dependencies are required locally.

## Commands

All commands must be run from the project root (`/Users/yerickson.arias/Documents/Diagramer`).

### Starting the environment

```bash
docker compose -f docker-compose.dev.yml up -d
```

### Frontend

| Action | Command |
|--------|---------|
| Run tests | `docker compose -f docker-compose.dev.yml exec frontend npm test` |
| Run build | `docker compose -f docker-compose.dev.yml exec frontend npm run build` |
| Run lint | `docker compose -f docker-compose.dev.yml exec frontend npm run lint` |
| Install a dependency | `docker compose -f docker-compose.dev.yml exec frontend npm install <package>` |
| Run a specific test | `docker compose -f docker-compose.dev.yml exec frontend npx vitest run <path>` |

### Backend

| Action | Command |
|--------|---------|
| Run tests | `docker compose -f docker-compose.dev.yml exec backend pytest` |
| Run a specific test | `docker compose -f docker-compose.dev.yml exec backend pytest <path>` |
| Install a dependency | `docker compose -f docker-compose.dev.yml exec backend pip install <package>` |
| Run linting | `docker compose -f docker-compose.dev.yml exec backend ruff check .` |

### Rebuilding containers

After changing `Dockerfile.dev`, `pyproject.toml`, or `package.json`:

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

## Rationale

- Ensures reproducible builds across all contributors.
- Eliminates "works on my machine" issues.
- Keeps the host machine clean of project-specific toolchains.
- Volume mounts provide live code reload during development without local installs.