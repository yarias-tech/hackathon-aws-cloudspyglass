output "ecr_repository_url" {
  description = "URL del repositorio ECR (usada en el pipeline CI/CD)"
  value       = aws_ecr_repository.app.repository_url
}

output "alb_dns_name" {
  description = "DNS del Application Load Balancer — URL pública de la app"
  value       = "http://${aws_lb.app.dns_name}"
}

output "ecs_cluster_name" {
  description = "Nombre del cluster ECS"
  value       = aws_ecs_cluster.app.name
}

output "ecs_service_name" {
  description = "Nombre del servicio ECS"
  value       = aws_ecs_service.app.name
}

output "cloudwatch_log_group" {
  description = "Nombre del grupo de logs en CloudWatch"
  value       = aws_cloudwatch_log_group.app.name
}

output "aws_account_id" {
  description = "ID de la cuenta AWS"
  value       = data.aws_caller_identity.current.account_id
}
