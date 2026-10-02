# Salidas del despliegue. `instance_public_ip` es el valor que el pipeline consume como
# secreto de host; `ssh_command` evita tener que reconstruir el comando a mano.

output "instance_public_ip" {
  description = "IP pública de la instancia. Es el valor del secreto EC2_HOST del pipeline."
  value       = aws_instance.web.public_ip
}

output "instance_public_dns" {
  description = "Nombre DNS público de la instancia."
  value       = aws_instance.web.public_dns
}

output "ssh_command" {
  description = "Comando de conexión SSH listo para pegar en la terminal del operador."
  value       = "ssh -i ~/.ssh/app2w-deploy ec2-user@${aws_instance.web.public_ip}"
}