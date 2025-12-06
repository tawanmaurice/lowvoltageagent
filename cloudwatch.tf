resource "aws_cloudwatch_event_rule" "low_voltage_schedule" {
  name                = "low-voltage-agent-schedule"
  description         = "Schedule to run the low-voltage lead agent"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "low_voltage_target" {
  rule      = aws_cloudwatch_event_rule.low_voltage_schedule.name
  target_id = "low-voltage-agent-target"
  arn       = aws_lambda_function.low_voltage_agent.arn
}

resource "aws_lambda_permission" "allow_cloudwatch_to_invoke" {
  statement_id  = "AllowExecutionFromCloudWatchLowVoltage"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.low_voltage_agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.low_voltage_schedule.arn
}
