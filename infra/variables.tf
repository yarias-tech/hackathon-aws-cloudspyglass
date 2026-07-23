variable "aws_region" {
  description = "Región de AWS donde se desplegará la infraestructura"
  type        = string
  default     = "us-east-1"
}

variable "vpc_id" {
  description = "ID del VPC existente donde se desplegará la infraestructura"
  type        = string
}

variable "subnet_ids" {
  description = "Lista de IDs de subnets públicas dentro del VPC (mínimo 2, en distintas AZs)"
  type        = list(string)
}

variable "app_name" {
  description = "Nombre de la aplicación (usado como prefijo en todos los recursos)"
  type        = string
  default     = "cloudspyglass"
}

variable "container_port" {
  description = "Puerto en el que escucha el contenedor"
  type        = number
  default     = 8080
}

variable "task_cpu" {
  description = "CPU para la tarea ECS (en unidades vCPU * 1024)"
  type        = string
  default     = "512"
}

variable "task_memory" {
  description = "Memoria para la tarea ECS (en MB)"
  type        = string
  default     = "1024"
}

variable "desired_count" {
  description = "Número de instancias del contenedor a correr"
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "Días de retención de logs en CloudWatch"
  type        = number
  default     = 7
}

variable "domain_name" {
  description = "Dominio para el certificado HTTPS (ej: app.example.com). Dejar vacío para solo HTTP."
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ARN de un certificado ACM existente. Si se provee, se usa en vez de crear uno nuevo."
  type        = string
  default     = ""
}
