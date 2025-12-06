variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "lambda_function_name" {
  description = "Name of the Lambda function"
  type        = string
  default     = "low-voltage-agent"
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for storing leads"
  type        = string
  default     = "low-voltage-leads-v1"
}

variable "google_api_key" {
  description = "Google Programmable Search API key"
  type        = string
}

variable "google_cx" {
  description = "Google Programmable Search custom search engine ID (CX)"
  type        = string
}

variable "schedule_expression" {
  description = "CloudWatch schedule expression for running the agent"
  type        = string
  default     = "rate(12 hours)"
}
