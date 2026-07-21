# CloudSpyglass — Project Structure

```
.
├── backend/                  # Python FastAPI backend
│   ├── main.py              # FastAPI app entry point, router registration
│   ├── exceptions.py        # Custom error classes and handlers
│   ├── models/              # Pydantic request/response models
│   │   ├── credentials.py
│   │   ├── diagram.py
│   │   ├── errors.py
│   │   ├── export.py
│   │   ├── filters.py
│   │   ├── resources.py
│   │   ├── scan.py
│   │   └── settings.py
│   ├── routes/              # API route handlers (one file per domain)
│   │   ├── credentials.py
│   │   ├── diagrams.py
│   │   ├── export.py
│   │   ├── filters.py
│   │   ├── images.py
│   │   ├── scan.py
│   │   └── settings.py
│   ├── services/            # Business logic layer
│   │   ├── credential_manager.py
│   │   ├── export_service.py
│   │   ├── filter_engine.py
│   │   ├── relationship_resolver.py
│   │   ├── scan_storage.py
│   │   └── scanner.py
│   ├── tests/               # pytest + Hypothesis tests
│   ├── pyproject.toml       # Python deps and config
│   └── Dockerfile.dev       # Dev container definition
│
├── frontend/                 # React + TypeScript frontend
│   ├── src/
│   │   ├── App.tsx          # Root component with routing
│   │   ├── main.tsx         # Vite entry point
│   │   ├── api/             # API client utilities
│   │   ├── components/      # Reusable UI components
│   │   ├── types/           # TypeScript interfaces/types
│   │   └── test/            # Test setup (vitest + jsdom)
│   ├── public/              # Static assets
│   ├── vite.config.ts       # Vite + Vitest config
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile.dev       # Dev container definition
│
├── infra/                    # Terraform IaC
│   ├── main.tf              # Provider, data sources
│   ├── ecs.tf              # ECS cluster and service
│   ├── alb.tf              # Application Load Balancer
│   ├── ecr.tf              # Container registry
│   ├── iam.tf              # IAM roles/policies
│   ├── security_groups.tf  # Security groups
│   ├── variables.tf        # Input variables
│   ├── outputs.tf          # Output values
│   └── terraform.tfvars    # Variable values
│
├── assets/                   # Static assets (icons, logos)
│   ├── icons/               # AWS architecture icons (SVG + PNG)
│   └── logo/                # Application logo
│
├── data/                     # Scan result JSON persistence (gitignored at runtime)
│
├── .github/workflows/        # CI/CD (backend, frontend, infra pipelines)
│
├── docker-compose.dev.yml   # Development multi-container setup
├── docker-compose.yml       # Production single-container setup
├── Dockerfile               # Multi-stage production build
├── nginx.conf               # Nginx reverse proxy config
└── supervisord.conf         # Process supervisor for production container
```

## Architecture Pattern

- **Backend**: Layered architecture — routes → services → models. Services are injected as module-level singletons.
- **Frontend**: Component-driven with colocated tests. Pages compose components; API calls happen in pages or dedicated hooks.
- **Data flow**: Frontend → `/api/*` → FastAPI routes → services → boto3/filesystem → response models → JSON.
