########################################
# DynamoDB table for travel agent leads
########################################

resource "aws_dynamodb_table" "travel_agent_leads" {
  name         = "travel-agent-leads-v1"
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "id"

  attribute {
    name = "id"
    type = "S"
  }

  table_class = "STANDARD"

  tags = {
    Name        = "travel-agent-leads-v1"
    Project     = "travel-agent-v1"
    Environment = "prod"
  }
}
