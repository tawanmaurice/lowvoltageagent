##############################################
# LOW VOLTAGE LAMBDA FUNCTION
##############################################

resource "aws_lambda_function" "low_voltage_agent" {
  function_name = "low-voltage-agent"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda.lambda_handler"
  runtime       = "python3.12"

  filename         = "lambda.zip"
  source_code_hash = filebase64sha256("lambda.zip")

  timeout     = 30
  memory_size = 512

  #############################
  # ENVIRONMENT VARIABLES
  #############################
  environment {
    variables = {
      GOOGLE_API_KEY = var.google_api_key
      GOOGLE_CX      = var.google_cx

      # DynamoDB table name passed as a simple variable
      TABLE_NAME     = var.table_name

      # Summary emails
      REPORT_EMAIL   = var.report_email      # you (Tawan)
      REPORT_EMAIL_2 = var.report_email_2    # Omar
    }
  }
}
