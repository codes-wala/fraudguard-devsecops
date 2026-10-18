variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-south-1"
}

variable "instance_type" {
  description = "EC2 instance type (t3.micro is free-tier eligible in most regions)"
  type        = string
  default     = "t3.micro"
}

variable "docker_image" {
  description = "Docker Hub image the server should run, for example myuser/fraudguard:latest"
  type        = string
  default     = "your-dockerhub-username/fraudguard:latest"
}

variable "allowed_http_cidrs" {
  description = "Who can open the website on port 80"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "ssh_cidr" {
  description = "Your public IP in CIDR form (1.2.3.4/32) to allow SSH. Leave empty to keep SSH closed."
  type        = string
  default     = ""
}

variable "key_name" {
  description = "Existing EC2 key pair name (only needed if you want SSH). Leave empty for none."
  type        = string
  default     = ""
}
