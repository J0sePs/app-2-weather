# Infraestructura AWS del predictor de Machu Picchu: una red pública mínima, un grupo
# de seguridad con SSH restringido y una instancia EC2 que se prepara sola al arrancar.
#
# `terraform apply` crea todo y `terraform destroy` lo elimina; no hay pasos manuales.

terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# Red pública
# ---------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name      = "app2w-vpc"
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name      = "app2w-igw"
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name      = "app2w-subnet-public"
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name      = "app2w-rt-public"
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}

# La asociación no admite bloque `tags`: su esquema sólo acepta `route_table_id`,
# `subnet_id` y `gateway_id`. Sigue siendo localizable porque tanto la subnet como la
# tabla de rutas están etiquetadas, que es como aparece en el inventario de la cuenta.
resource "aws_route_table_association" "public" {
  route_table_id = aws_route_table.public.id
  subnet_id      = aws_subnet.public.id
}

# ---------------------------------------------------------------------------
# Acceso
# ---------------------------------------------------------------------------

resource "aws_security_group" "web" {
  vpc_id = aws_vpc.main.id

  # SSH sólo desde la IP declarada por el operador. Nunca desde 0.0.0.0/0.
  ingress {
    description = "SSH desde la IP del operador"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip]
  }

  # La aplicación se sirve por Nginx en el puerto 80.
  ingress {
    description = "HTTP desde Internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Salida a Internet"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name      = "app2w-sg-web"
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}

# El par de claves se registra en AWS pero la clave privada nunca entra en Terraform:
# `public_key_path` apunta al archivo local del operador y sólo se lee su mitad pública.
resource "aws_key_pair" "deploy" {
  key_name   = "app2w-deploy"
  public_key = file(pathexpand(var.public_key_path))

  tags = {
    Name      = "app2w-keypair-deploy"
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Instancia
# ---------------------------------------------------------------------------

# Amazon Linux 2023 estándar para x86_64, la más reciente publicada por Amazon.
#
# El provider v6 llama a este argumento `name_regex` (antes `name_pattern`, que ya no
# existe), así que el glob del contrato se escribe como expresión regular.
#
# La expresión es deliberadamente estricta. Un glob flojo tipo `al2023-ami-*-x86_64`
# también captura las variantes que publica Amazon bajo el mismo prefijo, y con
# `most_recent` elige la más nueva de todas, que hoy es la optimizada para el acelerador
# AWS Neuron (`al2023-ami-ecs-neuron-hvm-...`). Exigir una versión numérica detrás de
# `al2023-ami-` descarta las variantes `minimal`, `ecs-hvm` y `ecs-neuron-hvm`, que no
# son la imagen base que espera el arranque.
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  # Amazon publica una imagen por versión de kernel (6.1, 6.12, 6.18...) con la misma
  # fecha de creación, así que `most_recent` las desempata como puede. Todas son la
  # misma AL2023 y cualquiera sirve; si cambia el desempate, el plan pedirá recrear la
  # instancia, que es el trade-off ya asumido por no fijar el `ami_id`.
  name_regex = "^al2023-ami-[0-9][0-9.]*-kernel-[0-9][0-9.]*-x86_64$"

  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "aws_instance" "web" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.web.id]
  key_name                    = aws_key_pair.deploy.key_name
  associate_public_ip_address = true

  # El script sigue siendo un archivo aparte; se codifica en base64 porque el provider
  # avisa si `user_data` se deja en claro dentro del estado.
  user_data_base64 = base64encode(file("${path.module}/user_data.sh"))

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name      = "app2w-ec2-web"
    Project   = var.project_name
    ManagedBy = "terraform"
  }
}