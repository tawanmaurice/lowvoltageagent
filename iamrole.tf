##############################################
# IAM ROLE FOR LOW VOLTAGE LAMBDA
##############################################

resource "aws_iam_role" "lambda_role" {
  name = "low-voltage-agent-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

########################################
# Basic CloudWatch Logs permissions
########################################

resource "aws_iam_role_policy_attachment" "lambda_basic_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

########################################
# DynamoDB permissions for low-voltage table
########################################

resource "aws_iam_role_policy" "lambda_dynamodb_policy" {
  name = "low-voltage-agent-dynamodb-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.low_voltage_leads.arn
      }
    ]
  })
}

########################################
# SES permissions – reports to you + Omar
########################################

resource "aws_iam_role_policy" "lambda_ses_policy" {
  name = "low-voltage-agent-ses-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = [
          "arn:aws:ses:us-east-1:276671279137:identity/tawanmaurice@gmail.com",
          "arn:aws:ses:us-east-1:276671279137:identity/oboyd@hdcnetworks.com"
        ]
      }
    ]
  })
}
