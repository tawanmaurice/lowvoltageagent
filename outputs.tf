output "lambda_function_name" {
  description = "Name of the low-voltage Lambda function"
  value       = aws_lambda_function.low_voltage_agent.function_name
}

output "lambda_function_arn" {
  description = "ARN of the low-voltage Lambda function"
  value       = aws_lambda_function.low_voltage_agent.arn
}
