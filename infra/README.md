# Infraestructura — CloudSpyGlass (Terraform)

Infraestructura en AWS usando **Terraform + ECS Fargate + ECR**.

## Estructura

```
infra/
├── main.tf                    # Provider, backend, data sources
├── variables.tf               # Variables configurables
├── outputs.tf                 # Valores de salida (URL, ARNs, etc.)
├── ecr.tf                     # Repositorio ECR + lifecycle policy
├── ecs.tf                     # Cluster, Task Definition y Service ECS
├── alb.tf                     # Application Load Balancer + Target Group
├── iam.tf                     # IAM Role para ECS Task Execution
├── security_groups.tf         # Security Groups para ALB y ECS
├── ecs-task-definition.json   # Template usado por el pipeline CI/CD
└── aws-cli-commands.md        # Comandos de diagnóstico útiles
```

## Arquitectura

```
Internet → ALB (puerto 80) → ECS Fargate (puerto 8080) → ECR (imagen Docker)
```

## Pre-requisitos

- [Terraform >= 1.5](https://developer.hashicorp.com/terraform/downloads)
- AWS CLI configurado (`aws configure`)
- Permisos IAM: `AmazonECS_FullAccess`, `AmazonEC2ContainerRegistryFullAccess`, `ElasticLoadBalancingFullAccess`, `IAMFullAccess`

## Despliegue inicial (solo una vez)

```bash
cd infra/

# 1. Inicializar Terraform
terraform init

# 2. Ver qué va a crear
terraform plan

# 3. Aplicar
terraform apply
```

Al finalizar, Terraform muestra los outputs:

```
alb_dns_name          = "http://cloudspyglass-alb-XXXXX.us-east-1.elb.amazonaws.com"
ecr_repository_url    = "ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/cloudspyglass"
ecs_cluster_name      = "cloudspyglass-cluster"
ecs_service_name      = "cloudspyglass-service"
```

## Deploys posteriores

A partir del despliegue inicial, **el pipeline CI/CD maneja todo automáticamente** al hacer push a `main`:

1. Build de la imagen Docker
2. Push a ECR
3. Update de la Task Definition con la nueva imagen
4. Deploy en ECS con zero-downtime

## Destruir la infra

```bash
cd infra/
terraform destroy
```

## Personalización

Edita `variables.tf` o pasa variables en el apply:

```bash
# Escalar a 2 instancias
terraform apply -var="desired_count=2"

# Cambiar región
terraform apply -var="aws_region=us-west-2"
```
