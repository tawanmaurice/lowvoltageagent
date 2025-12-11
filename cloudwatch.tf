##############################################
# CLOUDWATCH EVENT RULES FOR LOW VOLTAGE AGENT
##############################################

resource "aws_cloudwatch_event_rule" "low_voltage_morning" {
  name                = "low-voltage-agent-morning"
  description         = "Run low-voltage agent (New York) each morning"
  schedule_expression = var.schedule_expression_morning
}

resource "aws_cloudwatch_event_rule" "low_voltage_evening" {
  name                = "low-voltage-agent-evening"
  description         = "Run low-voltage agent (New York) each evening"
  schedule_expression = var.schedule_expression_evening
}

##############################################
# TARGETS
##############################################

resource "aws_cloudwatch_event_target" "low_voltage_target_morning" {
  rule      = aws_cloudwatch_event_rule.low_voltage_morning.name
  target_id = "low-voltage-lambda-morning"
  arn       = aws_lambda_function.low_voltage_agent.arn
}

resource "aws_cloudwatch_event_target" "low_voltage_target_evening" {
  rule      = aws_cloudwatch_event_rule.low_voltage_evening.name
  target_id = "low-voltage-lambda-evening"
  arn       = aws_lambda_function.low_voltage_agent.arn
}

##############################################
# PERMISSIONS FOR EVENTS TO INVOKE LAMBDA
##############################################

resource "aws_lambda_permission" "allow_morning" {
  statement_id  = "AllowExecutionFromCloudWatchMorningLowVoltage"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.low_voltage_agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.low_voltage_morning.arn
}

resource "aws_lambda_permission" "allow_evening" {
  statement_id  = "AllowExecutionFromCloudWatchEveningLowVoltage"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.low_voltage_agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.low_voltage_evening.arn
}
