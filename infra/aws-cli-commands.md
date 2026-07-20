# Comandos AWS CLI de referencia

## ECR

```bash
# Login al registro ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com

# Listar imágenes en el repositorio
aws ecr list-images --repository-name cloudspyglass --region us-east-1

# Eliminar imágenes antiguas (dejar solo las últimas 5)
aws ecr list-images --repository-name cloudspyglass --region us-east-1 \
  --query 'imageIds[*]' --output json
```

## ECS

```bash
# Ver estado del servicio
aws ecs describe-services \
  --cluster cloudspyglass-cluster \
  --services cloudspyglass-service \
  --region us-east-1 \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}'

# Ver tareas corriendo
aws ecs list-tasks \
  --cluster cloudspyglass-cluster \
  --service-name cloudspyglass-service \
  --region us-east-1

# Ver detalles de una tarea (reemplazar TASK_ARN)
aws ecs describe-tasks \
  --cluster cloudspyglass-cluster \
  --tasks TASK_ARN \
  --region us-east-1

# Forzar un nuevo deploy (sin cambios de imagen)
aws ecs update-service \
  --cluster cloudspyglass-cluster \
  --service cloudspyglass-service \
  --force-new-deployment \
  --region us-east-1

# Escalar el servicio (ej: 2 instancias)
aws ecs update-service \
  --cluster cloudspyglass-cluster \
  --service cloudspyglass-service \
  --desired-count 2 \
  --region us-east-1
```

## CloudWatch Logs

```bash
# Ver logs en tiempo real
aws logs tail /ecs/cloudspyglass --follow --region us-east-1

# Ver logs de las últimas 2 horas
aws logs tail /ecs/cloudspyglass \
  --since 2h \
  --region us-east-1
```

## ALB

```bash
# Obtener la URL del ALB
aws elbv2 describe-load-balancers \
  --names cloudspyglass-alb \
  --query 'LoadBalancers[0].DNSName' \
  --output text \
  --region us-east-1

# Ver estado del target group (health checks)
aws elbv2 describe-target-health \
  --target-group-arn $(aws elbv2 describe-target-groups \
    --names cloudspyglass-tg \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text --region us-east-1) \
  --region us-east-1
```

## Diagnóstico rápido

```bash
# Script para ver el estado completo
aws ecs describe-services \
  --cluster cloudspyglass-cluster \
  --services cloudspyglass-service \
  --region us-east-1 \
  --query 'services[0].events[:5]' \
  --output table
```
