resource "aws_cloudwatch_log_group" "low_voltage_agent_logs" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = 30
}

resource "aws_lambda_function" "low_voltage_agent" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_role.arn

  # IMPORTANT: we'll create this zip file later (lambda.py -> lambda.zip)
  filename         = "${path.module}/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda.zip")

  handler = "lambda.lambda_handler"
  runtime = "python3.11"

  timeout      = 900
  memory_size  = 512

  environment {
    variables = {
      TABLE_NAME     = var.dynamodb_table_name
      GOOGLE_API_KEY = var.google_api_key
      GOOGLE_CX      = var.google_cx
      LOG_LEVEL      = "INFO"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.low_voltage_agent_logs
  ]
}
