output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.web.id
}

output "public_ip" {
  description = "Public IP of the server"
  value       = aws_instance.web.public_ip
}

output "website_url" {
  description = "Open this in the browser (wait 2-3 minutes after apply)"
  value       = "http://${aws_instance.web.public_ip}"
}
