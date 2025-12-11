##############################################
# DYNAMODB TABLE FOR LOW-VOLTAGE LEADS
##############################################

resource "aws_dynamodb_table" "low_voltage_leads" {
  # Physical table name in AWS
  name         = "low-voltage-leads-v1"
  billing_mode = "PAY_PER_REQUEST"

  # Simple primary key
  hash_key = "id"

  attribute {
    name = "id"
    type = "S"
  }

  tags = {
    Project = "low-voltage-agent"
    Owner   = "Tawan"
  }
}
