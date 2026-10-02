# Entradas del módulo. Los valores por omisión son funcionales salvo `my_ip`, que es
# obligatoria a propósito: un valor por omisión para el origen de SSH sería un rango
# elegido por el código que nadie revisa, y su error es invisible hasta que ya hubo
# escaneo de puerto abierto.
#
# Este módulo usa `pathexpand()`, disponible desde Terraform 1.3. Con versiones
# anteriores `file()` no expande `~` y el apply falla con un error de fichero no
# encontrado sobre una ruta literal con tilde.

variable "aws_region" {
  description = "Región de AWS donde se crea la infraestructura."
  type        = string
  default     = "us-east-1"
}

variable "my_ip" {
  # Sin `default`: el despliegue falla de forma explícita en lugar de abrir el puerto
  # 22 a un rango que nadie ha revisado.
  description = "Prefijo CIDR /32 de la IP pública desde la que se accede por SSH. Ej.: 203.0.113.10/32"
  type        = string

  validation {
    condition     = can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", var.my_ip))
    error_message = "my_ip debe ser una IPv4 con prefijo /32, por ejemplo 203.0.113.10/32. Consulta tu IP pública con `curl -s https://checkip.amazonaws.com` y añade el /32."
  }

  validation {
    condition     = can(cidrhost(var.my_ip, 0)) && cidrhost(var.my_ip, 0) == split("/", var.my_ip)[0]
    error_message = "my_ip no es una dirección IPv4 válida."
  }
}

variable "public_key_path" {
  description = "Ruta del archivo de clave pública SSH que se registra como par de claves de la instancia. Admite el prefijo ~."
  type        = string
  default     = "~/.ssh/app2w-deploy.pub"

  validation {
    condition     = length(trimspace(var.public_key_path)) > 0
    error_message = "public_key_path no puede estar vacío."
  }
}

variable "project_name" {
  description = "Valor de la etiqueta Project que identifica los recursos de este proyecto."
  type        = string
  default     = "app-2-weather"
}