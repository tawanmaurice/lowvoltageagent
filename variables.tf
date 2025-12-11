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
# DynamoDB table
########################

variable "table_name" {
  description = "DynamoDB table name for low-voltage leads"
  type        = string
}

########################
# Email reporting
########################

variable "report_email" {
  description = "Primary email address for low-voltage reports (Tawan)"
  type        = string
}

variable "report_email_2" {
  description = "Secondary email address for low-voltage reports (Omar)"
  type        = string
  default     = ""
}

########################
# CloudWatch schedules
########################

variable "schedule_expression_morning" {
  description = "Schedule for morning low-voltage run"
  type        = string
}

variable "schedule_expression_evening" {
  description = "Schedule for evening low-voltage run"
  type        = string
}
