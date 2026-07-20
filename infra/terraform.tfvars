# =============================================================================
# CloudSpyGlass — Valores de infraestructura
# Completa los valores marcados con TODO antes de ejecutar terraform apply
# =============================================================================

# ── AWS ───────────────────────────────────────────────────────────────────────
aws_region = "us-east-1"

# ── Red ───────────────────────────────────────────────────────────────────────
# ID del VPC existente (ej: vpc-0abc123def456)
vpc_id = "vpc-0ffd43e594224fec2"

# Subnets públicas en distintas AZs (mínimo 2 para alta disponibilidad)
subnet_ids = [
  "subnet-0af942155cf978393",
  "subnet-062530c656644a1d6",
]

# ── Aplicación ────────────────────────────────────────────────────────────────
app_name       = "cloudspyglass"
container_port = 8080

# ── ECS / Fargate ─────────────────────────────────────────────────────────────
# CPU: 256 | 512 | 1024 | 2048 | 4096
# Memory: debe ser compatible con el CPU elegido
# https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-cpu-memory-error.html
task_cpu    = "512"
task_memory = "1024"

# Número de instancias del contenedor corriendo simultáneamente
desired_count = 1

# ── Logs ──────────────────────────────────────────────────────────────────────
log_retention_days = 7
