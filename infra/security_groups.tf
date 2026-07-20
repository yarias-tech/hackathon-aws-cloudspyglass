# ── Security Group: ALB ───────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name        = "${var.app_name}-alb-sg"
  description = "Permite tráfico HTTP entrante al ALB"
  vpc_id      = data.aws_vpc.main.id

  ingress {
    description = "HTTP desde internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Todo el tráfico saliente"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.app_name}-alb-sg"
  }
}

# ── Security Group: ECS Tasks ─────────────────────────────────────────────────

resource "aws_security_group" "ecs" {
  name        = "${var.app_name}-ecs-sg"
  description = "Permite tráfico desde el ALB a las tareas ECS"
  vpc_id      = data.aws_vpc.main.id

  ingress {
    description     = "Tráfico desde el ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Todo el tráfico saliente (necesario para ECR, CloudWatch, etc.)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.app_name}-ecs-sg"
  }
}
