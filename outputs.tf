output "lambda_function_name" {
  description = "Low-voltage agent Lambda function name"
  value       = aws_lambda_function.low_voltage_agent.function_name
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for low-voltage leads"
  value       = aws_dynamodb_table.low_voltage_leads.name
}
