# CloudSpyglass

Herramienta de visualización de infraestructura AWS. Escanea una cuenta AWS en múltiples regiones, descubre recursos y sus relaciones, y genera un diagrama interactivo de arquitectura en el navegador.

---

## Tabla de Contenidos

- [Descripción](#descripción)
- [Arquitectura General](#arquitectura-general)
- [Diagrama de Infraestructura (AWS)](#diagrama-de-infraestructura-aws)
- [Flujo de Datos](#flujo-de-datos)
- [Stack Tecnológico](#stack-tecnológico)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Guía de Implementación Paso a Paso](#guía-de-implementación-paso-a-paso)
- [Desarrollo Local](#desarrollo-local)
- [API Endpoints](#api-endpoints)
- [CI/CD Pipeline](#cicd-pipeline)

---

## Descripción

CloudSpyglass permite a desarrolladores, SREs y arquitectos cloud obtener una vista rápida y visual de su infraestructura AWS sin navegar manualmente por la consola de AWS.

**Capacidades principales:**

- Gestión de credenciales AWS (UI o cadena boto3 por defecto)
- Escaneo multi-región de 30+ tipos de recursos (EC2, VPC, S3, Lambda, RDS, ECS, ALB, IAM, DynamoDB, CloudFront, Route53, etc.)
- Resolución de relaciones (network, IAM, event, data) entre recursos
- Diagrama interactivo pan-and-zoom con auto-layout (dagre)
- Filtrado por tags (lógica AND) y tipo de recurso (lógica OR)
- Exportación a PDF, PNG y SVG
- Persistencia de resultados como JSON por cuenta
- Auto-refresh configurable

---

## Arquitectura General

```
┌─────────────────────────────────────────────────────────────────────┐
│                          NAVEGADOR                                   │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  React 19 + React Flow + dagre                                │  │
│  │                                                               │  │
│  │  DiagramPage ─┬─ DiagramCanvas (React Flow + dagre layout)    │  │
│  │               ├─ FilterBar (tag + type filters)               │  │
│  │               ├─ ScanControls (trigger/cancel/auto-refresh)   │  │
│  │               ├─ ExportMenu (PDF/PNG/SVG)                     │  │
│  │               ├─ DetailPanel (resource metadata)              │  │
│  │               └─ RegionScanSelector                           │  │
│  │                                                               │  │
│  │  SettingsPage ── auto-refresh interval + region selection     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │ /api/*                                │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────┐
│                     CONTENEDOR PRODUCCIÓN                            │
│                              │                                      │
│  ┌───────────┐    ┌─────────▼─────────┐    ┌───────────────────┐   │
│  │  Nginx    │───▶│  Uvicorn (FastAPI) │───▶│  boto3 → AWS APIs │   │
│  │  :8080    │    │  :8000             │    └───────────────────┘   │
│  │           │    │                    │                            │
│  │ Static /  │    │  Routes:           │    ┌───────────────────┐   │
│  │ SPA serve │    │  • credentials     │───▶│  data/*.json      │   │
│  └───────────┘    │  • scan            │    │  (persistencia)   │   │
│                   │  • diagrams        │    └───────────────────┘   │
│  supervisord      │  • filters         │                            │
│  orquesta ambos   │  • export          │    ┌───────────────────┐   │
│  procesos         │  • images          │───▶│  exports/         │   │
│                   │  • settings        │    │  (PDF/PNG/SVG)    │   │
│                   └────────────────────┘    └───────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Diagrama de Infraestructura (AWS)

```
                         ┌──────────────────┐
                         │    Internet      │
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │  ALB (port 80/443)│
                         │  cloudspyglass-alb│
                         │                  │
                         │  HTTP → HTTPS    │
                         │  redirect (301)  │
                         └────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │     Security Group: ALB    │
                    │  Ingress: 80, 443 (0.0.0.0/0)│
                    └─────────────┼─────────────┘
                                  │
                         ┌────────▼─────────┐
                         │  Target Group    │
                         │  :8080 /api/health│
                         └────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │  Security Group: ECS       │
                    │  Ingress: 8080 (from ALB SG)│
                    └─────────────┼─────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │          ECS Fargate Cluster           │
              │          cloudspyglass-cluster         │
              │                                       │
              │  ┌─────────────────────────────────┐  │
              │  │  Task: cloudspyglass-task        │  │
              │  │  CPU: 512 | Memory: 1024 MB     │  │
              │  │                                 │  │
              │  │  Container: cloudspyglass        │  │
              │  │  Image: ECR/cloudspyglass:latest │  │
              │  │  Port: 8080                     │  │
              │  │                                 │  │
              │  │  [Nginx :8080] + [Uvicorn :8000]│  │
              │  └─────────────────────────────────┘  │
              └───────────────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
     ┌────────▼───────┐  ┌───────▼────────┐  ┌──────▼──────┐
     │  ECR           │  │  CloudWatch    │  │  S3 Backend │
     │  cloudspyglass │  │  /ecs/cloud... │  │  (tfstate)  │
     │  (10 img max)  │  │  (7 días ret.) │  │             │
     └────────────────┘  └────────────────┘  └─────────────┘
```

**Componentes AWS:**

| Recurso | Propósito |
|---------|-----------|
| ALB | Balanceador público, HTTPS con ACM, health checks |
| ECS Fargate | Contenedor serverless, sin gestión de servidores |
| ECR | Registro de imágenes Docker, lifecycle de 10 imágenes |
| CloudWatch Logs | Logs centralizados, retención 7 días |
| IAM Role | Execution role para pull de ECR y push de logs |
| Security Groups | ALB (80/443 público) → ECS (8080 privado) |
| ACM | Certificado TLS para HTTPS (opcional) |
| S3 | Backend de estado de Terraform |

---

## Flujo de Datos

```
┌──────────┐    POST /api/credentials     ┌───────────────────┐
│  Usuario │ ─────────────────────────────▶│ CredentialManager │
│          │                               │ (STS validation)  │
└────┬─────┘                               └─────────┬─────────┘
     │                                               │
     │  POST /api/scan                               │ get_boto3_session()
     │                                               ▼
     │         ┌──────────────────────────────────────────────────┐
     │         │                  Scanner                          │
     │         │                                                  │
     │         │  1. Descubre regiones habilitadas                │
     │         │  2. Escanea recursos globales (S3, IAM, CF, R53) │
     │         │  3. Escanea regiones en paralelo (5 a la vez)    │
     │         │  4. Retry con backoff exponencial (hasta 5x)     │
     │         │  5. Timeout: 360s/región, 1800s total            │
     │         └───────────────────────┬──────────────────────────┘
     │                                 │
     │                                 ▼
     │         ┌──────────────────────────────────────────────────┐
     │         │           RelationshipResolver                    │
     │         │                                                  │
     │         │  Analiza configuraciones para detectar:          │
     │         │  • Network: VPC, Subnet, SG, ELB targets        │
     │         │  • IAM: Roles asociados a servicios             │
     │         │  • Event: SNS→Lambda, SQS→Lambda, S3 events     │
     │         │  • Data: Cross-account, unresolved refs          │
     │         └───────────────────────┬──────────────────────────┘
     │                                 │
     │                                 ▼
     │         ┌──────────────────────────────────────────────────┐
     │         │              ScanStorage                          │
     │         │  Persiste resultado como JSON (atomic write)     │
     │         │  Un archivo por account_id en data/              │
     │         └──────────────────────────────────────────────────┘
     │
     │  GET /api/diagrams/latest
     │                                 ┌──────────────────────────┐
     │         ┌──────────────────────▶│      FilterEngine        │
     │         │                       │                          │
     │         │                       │  Tags: AND logic         │
     │         │                       │  Types: OR logic         │
     │         │                       │  Combined: intersection  │
     │         │                       └────────────┬─────────────┘
     │         │                                    │
     │         │                                    ▼
     │         │                       ┌──────────────────────────┐
     ◀─────────┼───────────────────────│  DiagramData (JSON)     │
               │                       │  { nodes, edges,        │
               │                       │    account_id, ... }    │
               │                       └──────────────────────────┘
               │
               │  POST /api/export
               │                       ┌──────────────────────────┐
               └──────────────────────▶│     ExportService        │
                                       │                          │
                                       │  SVG → cairosvg → PNG   │
                                       │  SVG → cairosvg → PDF   │
                                       │  Timeout: 30s           │
                                       │  Max size: 50 MB        │
                                       └──────────────────────────┘
```

---

## Stack Tecnológico

### Backend
| Tecnología | Versión | Propósito |
|-----------|---------|-----------|
| Python | 3.12+ | Lenguaje principal |
| FastAPI | ≥0.115 | Framework web async |
| Uvicorn | ≥0.30 | Servidor ASGI |
| boto3 | ≥1.35 | SDK de AWS |
| Pydantic | v2 | Validación de datos |
| cairosvg | ≥2.7 | Renderizado SVG→PNG/PDF |

### Frontend
| Tecnología | Versión | Propósito |
|-----------|---------|-----------|
| React | 19 | UI framework |
| TypeScript | 6 | Type safety |
| Vite | 8 | Bundler |
| @xyflow/react | 12 | Diagramas interactivos |
| dagre | 0.8 | Auto-layout de grafos |
| jspdf + html2canvas | - | Export client-side |
| React Router | 7 | Routing SPA |

### Infraestructura
| Tecnología | Propósito |
|-----------|-----------|
| Terraform (~5.0) | IaC |
| ECS Fargate | Compute serverless |
| ALB | Load balancing + HTTPS |
| ECR | Container registry |
| Docker (multi-stage) | Imagen de producción |
| Nginx + supervisord | Reverse proxy + process manager |

### Testing
| Herramienta | Uso |
|-------------|-----|
| pytest + pytest-asyncio | Tests backend |
| Hypothesis | Property-based testing (backend) |
| moto | AWS mocking |
| Vitest + Testing Library | Tests frontend |
| fast-check | Property-based testing (frontend) |
| MSW | API mocking (frontend) |

---

## Estructura del Proyecto

```
.
├── backend/
│   ├── main.py                 # Entry point FastAPI, registro de routers
│   ├── dependencies.py         # Inyección de dependencias (singletons)
│   ├── exceptions.py           # Error handling centralizado
│   ├── models/                 # Pydantic models (request/response)
│   │   ├── credentials.py     # CredentialSubmission, CredentialStatus
│   │   ├── diagram.py         # DiagramNode, DiagramEdge, DiagramData
│   │   ├── errors.py          # ErrorResponse estándar
│   │   ├── export.py          # ExportRequest, ExportResult
│   │   ├── filters.py         # FilterCriteria, TagFilter, TagSuggestion
│   │   ├── resources.py       # Resource, Relationship
│   │   ├── scan.py            # ScanRequest, ScanResult, RegionFailure
│   │   └── settings.py        # AppSettings, AutoRefreshInterval
│   ├── routes/                 # API route handlers
│   │   ├── credentials.py     # POST/GET/DELETE /api/credentials
│   │   ├── scan.py            # POST/GET /api/scan (background task)
│   │   ├── diagrams.py        # GET /api/diagrams/latest[/filtered]
│   │   ├── filters.py         # GET /api/tags/suggestions
│   │   ├── export.py          # POST /api/export, GET download
│   │   ├── images.py          # GET /api/images/icons/{service_type}
│   │   └── settings.py        # GET/PUT /api/settings
│   ├── services/               # Lógica de negocio
│   │   ├── credential_manager.py  # Almacenamiento in-memory + STS validation
│   │   ├── scanner.py             # Multi-region parallel scanning
│   │   ├── relationship_resolver.py # Detección de relaciones entre recursos
│   │   ├── filter_engine.py       # Filtrado server-side
│   │   ├── export_service.py      # Generación SVG/PNG/PDF
│   │   └── scan_storage.py        # Persistencia JSON atómica
│   ├── tests/                  # pytest + Hypothesis
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Root con BrowserRouter + ErrorBoundary
│   │   ├── pages/
│   │   │   ├── DiagramPage.tsx # Página principal (canvas + controls)
│   │   │   └── SettingsPage.tsx
│   │   ├── components/
│   │   │   ├── DiagramCanvas.tsx      # React Flow + dagre layout
│   │   │   ├── ResourceNode.tsx       # Nodo custom con icono AWS
│   │   │   ├── RelationshipEdge.tsx   # Edge color-coded + tooltip
│   │   │   ├── FilterBar.tsx          # Filtros tag + type
│   │   │   ├── ScanControls.tsx       # Trigger/cancel scan
│   │   │   ├── ExportMenu.tsx         # Export PDF/PNG/SVG
│   │   │   ├── DetailPanel.tsx        # Metadata del recurso
│   │   │   ├── NavHeader.tsx          # Navegación
│   │   │   ├── ErrorBanner.tsx        # Errores globales
│   │   │   └── RegionScanSelector.tsx # Selector de regiones
│   │   ├── api/apiClient.ts   # HTTP client con error handling
│   │   └── types/             # TypeScript interfaces
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   └── package.json
│
├── infra/                      # Terraform
│   ├── main.tf                # Provider, data sources, S3 backend
│   ├── ecs.tf                 # Cluster, task definition, service
│   ├── alb.tf                 # ALB, target group, listeners HTTP/HTTPS
│   ├── ecr.tf                 # Repository + lifecycle policy
│   ├── iam.tf                 # ECS execution role + service-linked role
│   ├── security_groups.tf     # ALB SG + ECS SG
│   ├── variables.tf           # Inputs
│   ├── outputs.tf             # ECR URL, ALB DNS, cluster/service names
│   └── terraform.tfvars       # Valores de configuración
│
├── .github/workflows/
│   ├── deploy.yml             # Build & Deploy (Docker → ECR → ECS)
│   └── infra.yml              # Terraform apply/destroy (manual)
│
├── Dockerfile                 # Multi-stage production build
├── docker-compose.dev.yml     # Desarrollo local (hot-reload)
├── docker-compose.yml         # Producción local (single container)
├── nginx.conf                 # Reverse proxy config
└── supervisord.conf           # Process manager (nginx + uvicorn)
```

---

## Guía de Implementación Paso a Paso

### Prerrequisitos

- Docker y Docker Compose instalados
- Cuenta AWS con permisos de administrador
- Terraform ≥ 1.5
- AWS CLI configurado
- Repositorio en GitHub con los secrets configurados

### Paso 1: Clonar el repositorio

```bash
git clone <repo-url>
cd hackathon-aws-cloudspyglass
```

### Paso 2: Configurar secrets en GitHub

En **Settings → Secrets and variables → Actions** del repositorio:

| Secret | Descripción |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | Access key de IAM user con permisos ECR + ECS |
| `AWS_SECRET_ACCESS_KEY` | Secret key correspondiente |

Permisos IAM requeridos: `ecr:*`, `ecs:UpdateService`, `ecs:RegisterTaskDefinition`, `ecs:DescribeServices`, `iam:PassRole`, `logs:*`.

### Paso 3: Crear la infraestructura con Terraform

```bash
cd infra

# Configurar variables en terraform.tfvars
# - vpc_id: ID de tu VPC
# - subnet_ids: Al menos 2 subnets públicas (con Internet Gateway)
# - certificate_arn: (opcional) ARN de certificado ACM para HTTPS

terraform init
terraform plan -var-file="terraform.tfvars"
terraform apply -var-file="terraform.tfvars"
```

Recursos creados:
- ECS Cluster + Service + Task Definition
- ALB + Target Group + Listeners (HTTP y opcionalmente HTTPS)
- ECR Repository (lifecycle: 10 imágenes max)
- CloudWatch Log Group (retención: 7 días)
- IAM Execution Role
- Security Groups (ALB público → ECS privado)

### Paso 4: Primer deploy

Hay dos formas de triggerear el deploy:

**Opción A: Push a main**
```bash
git push origin main
```
El pipeline se activa automáticamente con cambios en `backend/`, `frontend/`, `Dockerfile`, `nginx.conf`, o `supervisord.conf`.

**Opción B: Manual (workflow_dispatch)**

Ir a **Actions → Build & Deploy → Run workflow**.

### Paso 5: Verificar el deploy

```bash
# Obtener la URL del ALB
aws elbv2 describe-load-balancers --names cloudspyglass-alb \
  --query 'LoadBalancers[0].DNSName' --output text

# Probar health check
curl http://<ALB_DNS>/api/health
# Respuesta: {"status": "ok"}

# Ver logs
aws logs tail /ecs/cloudspyglass --since 10m
```

### Paso 6: Configurar HTTPS (opcional)

1. Solicitar certificado en ACM:
```bash
aws acm request-certificate \
  --domain-name tu-dominio.com \
  --validation-method DNS
```

2. Validar el certificado (agregar CNAME en DNS).

3. Agregar en `terraform.tfvars`:
```hcl
certificate_arn = "arn:aws:acm:us-east-1:ACCOUNT:certificate/xxxxx"
```

4. Aplicar: `terraform apply`

5. Crear CNAME en DNS apuntando al ALB DNS.

---

## Desarrollo Local

Todo corre dentro de Docker. No se necesita Node.js ni Python instalado localmente.

### Levantar el entorno

```bash
docker compose -f docker-compose.dev.yml up -d
```

### Acceder

- **Frontend**: http://localhost:5173 (hot-reload)
- **Backend**: http://localhost:8000 (auto-restart)
- **API Health**: http://localhost:8000/api/health

El frontend en 5173 proxea automáticamente `/api` al backend en 8000.

### Comandos útiles

| Acción | Comando |
|--------|---------|
| Bajar entorno | `docker compose -f docker-compose.dev.yml down` |
| Reconstruir (tras cambios en deps) | `docker compose -f docker-compose.dev.yml up -d --build` |
| Tests backend | `docker compose -f docker-compose.dev.yml exec backend pytest` |
| Tests frontend | `docker compose -f docker-compose.dev.yml exec frontend npm test` |
| Lint backend | `docker compose -f docker-compose.dev.yml exec backend ruff check .` |
| Lint frontend | `docker compose -f docker-compose.dev.yml exec frontend npm run lint` |

### Probar imagen de producción localmente

```bash
docker build -t cloudspyglass .
docker run -p 8080:8080 cloudspyglass
# Acceder en http://localhost:8080
```

---

## API Endpoints

### Credenciales
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/credentials` | Enviar y validar credenciales AWS |
| GET | `/api/credentials/status` | Estado de conexión actual |
| DELETE | `/api/credentials` | Limpiar credenciales de memoria |

### Escaneo
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/scan` | Iniciar escaneo (background) |
| POST | `/api/scan/cancel` | Cancelar escaneo en curso |
| GET | `/api/scan/status` | Progreso del escaneo |

### Diagramas
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/diagrams/latest` | Diagrama completo sin filtros |
| GET | `/api/diagrams/latest/filtered` | Diagrama filtrado (query params) |
| GET | `/api/resources/{arn}` | Detalle de un recurso |

### Filtros
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/tags/suggestions?prefix=` | Autocompletado de tags |

### Exportación
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/export` | Generar exportación (PDF/PNG/SVG) |
| GET | `/api/export/download/{filename}` | Descargar archivo exportado |

### Configuración
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/settings` | Obtener configuración actual |
| PUT | `/api/settings` | Actualizar configuración |

### Imágenes
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/images/icons/{service_type}` | Icono SVG de un servicio AWS |

### Health
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/health` | Health check |

---

## CI/CD Pipeline

### deploy.yml — Build & Deploy

```
Trigger: push a main (backend/**, frontend/**, Dockerfile, nginx.conf, supervisord.conf)
         + workflow_dispatch (manual)

┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│  Checkout   │───▶│  Login ECR   │───▶│  Docker Build │───▶│  Push ECR    │
│             │    │              │    │  (multi-stage)│    │  :sha + :latest│
└─────────────┘    └──────────────┘    └───────────────┘    └──────┬───────┘
                                                                   │
                   ┌──────────────┐    ┌───────────────┐           │
                   │  Deploy ECS  │◀───│  Render Task  │◀──────────┘
                   │  (wait for   │    │  Definition   │
                   │   stability) │    │  (new image)  │
                   └──────────────┘    └───────────────┘
```

### infra.yml — Terraform

```
Trigger: workflow_dispatch (manual) con opción apply/destroy

┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│  Checkout   │───▶│  Terraform   │───▶│  fmt + validate│───▶│ apply/destroy│
│             │    │  Init        │    │               │    │              │
└─────────────┘    └──────────────┘    └───────────────┘    └──────────────┘
```

---

## Tipos de Recursos Soportados

El scanner detecta los siguientes tipos de recursos AWS:

**Globales** (escaneados una vez):
- S3, IAM Roles, CloudFront, Route53, ECR

**Regionales** (escaneados por región):
- EC2, Security Groups, VPC, Subnets, Lambda, RDS
- ALB, NLB, ECS, SNS, SQS, DynamoDB, API Gateway
- EKS, ElastiCache, EBS, Elastic IP, NAT Gateway
- Transit Gateway, VPN Gateway, Step Functions, Kinesis
- Secrets Manager, Redshift, OpenSearch, CodePipeline, Glue

---

## Relaciones Detectadas

| Categoría | Ejemplo | Visualización |
|-----------|---------|---------------|
| Network | EC2 → Security Group, ALB → Target | Línea azul sólida |
| IAM | Lambda → IAM Role, ECS → Execution Role | Línea verde punteada |
| Event | SNS → Lambda, SQS → Lambda, S3 events | Línea naranja animada |
| Data | DynamoDB streams, cross-account refs | Línea gris |

---

## Licencia

Proyecto interno - Hackathon AWS
