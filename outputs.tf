output "lambda_function_name" {
  description = "Name of the travel agent Lambda function"
  value       = aws_lambda_function.travel_agent.function_name
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table used for travel agent leads"
  value       = aws_dynamodb_table.travel_agent_leads.name
}
