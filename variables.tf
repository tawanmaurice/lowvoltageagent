########################
# Provider / region
########################

variable "aws_region" {
  description = "AWS region to deploy resources in"
  type        = string
}

########################
# Google Custom Search
########################

variable "google_api_key" {
  description = "Google Programmable Search API key"
  type        = string
}

variable "google_cx" {
  description = "Google Programmable Search CX identifier"
  type        = string
}

########################
# Email reporting
########################

variable "report_email" {
  description = "Email address to send travel agent summary reports to"
  type        = string
}

########################
# CloudWatch schedules
########################

variable "schedule_expression_morning" {
  description = "CloudWatch schedule expression for the morning travel-agent run"
  type        = string
}

variable "schedule_expression_evening" {
  description = "CloudWatch schedule expression for the evening travel-agent run"
  type        = string
}
