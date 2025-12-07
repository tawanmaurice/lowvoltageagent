########################################
# CloudWatch Event Rules (schedules)
########################################

resource "aws_cloudwatch_event_rule" "travel_agent_schedule_morning" {
  name                = "travel-agent-schedule-morning"
  description         = "Run travel-agent-v1 Lambda in the morning"
  schedule_expression = var.schedule_expression_morning
}

resource "aws_cloudwatch_event_rule" "travel_agent_schedule_evening" {
  name                = "travel-agent-schedule-evening"
  description         = "Run travel-agent-v1 Lambda in the evening"
  schedule_expression = var.schedule_expression_evening
}

########################################
# Targets – point rules at Lambda
########################################

resource "aws_cloudwatch_event_target" "travel_agent_target_morning" {
  rule      = aws_cloudwatch_event_rule.travel_agent_schedule_morning.name
  target_id = "travel-agent-target-morning"
  arn       = aws_lambda_function.travel_agent.arn
}

resource "aws_cloudwatch_event_target" "travel_agent_target_evening" {
  rule      = aws_cloudwatch_event_rule.travel_agent_schedule_evening.name
  target_id = "travel-agent-target-evening"
  arn       = aws_lambda_function.travel_agent.arn
}

########################################
# Lambda permissions – allow Events to invoke
########################################

resource "aws_lambda_permission" "allow_morning" {
  statement_id  = "AllowExecutionFromCloudWatchTravelMorning"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.travel_agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.travel_agent_schedule_morning.arn
}

resource "aws_lambda_permission" "allow_evening" {
  statement_id  = "AllowExecutionFromCloudWatchTravelEvening"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.travel_agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.travel_agent_schedule_evening.arn
}
