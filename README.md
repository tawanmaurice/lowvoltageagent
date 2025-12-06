
# Low Voltage Agent

The **Low Voltage Agent** is an automated lead generation tool built with Terraform and AWS Lambda. It scrapes the web for low voltage contractor opportunities and stores structured results in DynamoDB for further outreach and follow-up automation.

---

## 🚀 Features

- AWS Lambda function written in Python
- Daily Google search scraping
- Automatic removal of duplicate results
- DynamoDB storage for long-term lead tracking
- Infrastructure defined completely in Terraform
- Secure `.gitignore` policy to keep secrets and state files out of version control

---

## 🧱 Project Structure



lowvoltageagent/
├── cloudwatch.tf # CloudWatch schedules and lambda logging
├── dynamo.tf # DynamoDB table setup
├── iamrole.tf # Lambda execution policy + DynamoDB access
├── lambda.py # Main scraper logic
├── lambda.tf # Lambda function resource
├── outputs.tf # Output values after terraform apply
├── provider.tf # AWS provider configuration
├── variables.tf # User-configurable inputs (table name, region, etc.)
└── .gitignore # Secret and state safety


---

## 🔐 Secrets & Sensitive Files

The following files **must NOT** be committed:

- `terraform.tfvars`
- `terraform.tfstate`
- `terraform.tfstate.backup`
- `.terraform/`
- `lambda.zip`
- `tfplan`

These are protected by `.gitignore`.

> ⚠️ IMPORTANT: Create a file named **`terraform.tfvars`** locally with your credentials, but do not commit it.

Example:

```hcl
google_api_key     = "YOUR_API_KEY"
google_cx          = "YOUR_GOOGLE_CX"
dynamodb_table_name = "low-voltage-leads-v1"
aws_region         = "us-east-1"

🧩 Requirements

AWS account

Terraform CLI

Python 3.9 or later

IAM user with Lambda + DynamoDB permissions

Google Programmable Search Engine (API key + CX)

⚙️ Deployment

Initialize Terraform:

terraform init


Plan the infrastructure:

terraform plan -out tfplan


Apply:

terraform apply tfplan

🧪 Test Locally

To test Lambda locally:

python lambda.py


(Requires environment variables to be set manually.)

📦 DynamoDB Schema

The agent stores items in DynamoDB with fields like:

{
  "id": "HASHED_UNIQUE_ID",
  "url": "https://example.com",
  "title": "Low Voltage Contractor RFP",
  "snippet": "Bid due January 15th...",
  "source": "low-voltage-agent",
  "query": "low voltage contractor New Jersey office"
}

🛡 Security

This project includes:

Least-privilege IAM roles for Lambda

Secure .gitignore preventing secrets from being pushed

CloudWatch logging enabled for audits

Safely stored credential process via Terraform variables

📌 Roadmap

 Add automatic CloudWatch schedule (daily scraping)

 Add SQS for lead notification

 Add SES or Brevo email sender Lambda

 Add Multi-Agent architecture

 Convert to CI/CD with GitHub Actions

 Add remote Terraform backend in S3 + DynamoDB state locking

📖 License

This project is proprietary to Tawan Maurice Perry.

Not for resale or redistribution without written permission.
