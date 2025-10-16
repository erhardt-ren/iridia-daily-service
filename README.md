# Iridia Daily

Iridia Daily is a serverless email service that delivers fascinating scientific facts from recently published research papers directly to your inbox. Built on AWS using Lambda, Bedrock (Claude), and SNS.

## Features

- **Real Research**: Pulls from actual PubMed papers published in the last week
- **AI-Powered**: Uses Claude 3.5 Sonnet to transform complex research into accessible facts
- **Email Delivery**: Daily notifications via AWS SNS
- **Serverless**: Completely serverless architecture - costs pennies per month
- **Source Links**: Every fact includes a link to the original research paper
- **Scheduled**: Runs automatically on your preferred schedule
- **Scalable**: Broadcast same fact to unlimited subscribers

## Architecture

```
EventBridge (Daily Trigger)
    ↓
Lambda Function
    ↓
    ├─→ PubMed API (Fetch recent papers)
    ├─→ AWS Bedrock (Generate accessible fact)
    └─→ SNS Topic (Broadcast to subscribers)
```

**Tech Stack:**
- **Runtime**: Python 3.12
- **Infrastructure**: AWS SAM (Infrastructure as Code)
- **Services**: Lambda, Bedrock, SNS, EventBridge, CloudWatch
- **AI Model**: Anthropic Claude 3.5 Sonnet v2

## Cost

(Under Construction)

## Quick Start

### Prerequisites

- AWS Account with Bedrock access enabled
- AWS CLI configured
- AWS SAM CLI installed
- Python 3.12
- Docker (optional, for local testing)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/Iridia Daily.git
cd Iridia Daily
```

2. **Enable Bedrock Access**
- Go to AWS Console → Bedrock → Model Access
- Enable "Claude 3.5 Sonnet v2"
- Wait for "Access granted" status

3. **Deploy**
```bash
# Build the application
sam build

# Deploy with guided setup
sam deploy --guided

# Follow prompts:
# - Stack Name: Iridia Daily
# - AWS Region: us-east-1
# - Parameter EmailAddress: your-email@example.com
# - Allow IAM role creation: Y
# - Save arguments to config: Y
```

4. **Confirm Email Subscription**
- Check your email for SNS confirmation
- Click the confirmation link

5. **Test It!**
```bash
# Manually trigger the function
aws lambda invoke \
  --function-name daily-fact-generator \
  --cli-binary-format raw-in-base64-out \
  response.json

# Check your email for the fact!
```

## How to configure the newsletter

### Change Schedule

Edit `template.yaml` to change when facts are sent:

```yaml
Schedule: cron(0 11 * * ? *)  # Daily at 7am EST
```

### Customize Topics

Edit `src/iridia-daily/lambda_function.py` to change research fields:

```python
# Current (broad science)
query = urllib.parse.quote(f"(biology[MeSH] OR physics OR neuroscience OR astronomy) AND {date_range}[PDAT]")

# Focus on specific field (e.g., space science)
query = urllib.parse.quote(f"(astrophysics OR cosmology OR astronomy) AND {date_range}[PDAT]")
```

## Development

### Local Testing

```bash
# Build
sam build

# Test locally (requires Docker)
sam local invoke FactGeneratorFunction

# View logs
sam logs --tail --name FactGeneratorFunction
```

### Deploy Updates

__*To be migrated to a proper CI/CD pipeline eventually*__
```bash
# After making changes
sam build && sam deploy
```

### View Logs

Under construction

## 🐛 Troubleshooting

### No email received?
1. Check you confirmed the SNS subscription
2. Check spam folder
3. View Lambda logs in CloudWatch

### Bedrock "Access Denied" error?
1. Enable Claude 3.5 Sonnet in AWS Console → Bedrock → Model Access
2. Ensure you're using the inference profile
3. Verify IAM permissions in template.yaml

### "Rate exceeded" error?
Wait 1 minute between deployments. CloudFormation has rate limits.

## Future Improvements
- **Implement Proper Testing**
- **Implement Email List Subscribe/Unsubscribe**
- **Create PR Template**
- **Add License**
- **Implement CI/CD** so that much of the building/testing/deploying can be automated
- **Web archive** hosted on S3 + CloudFront

## License

Please refer to the project license provided in the file LICENSE.

## Acknowledgments

- **PubMed/NCBI** for providing free access to research papers
- **Anthropic** for Claude AI via AWS Bedrock
- **AWS SAM** for making serverless deployment simple

## Contact

Have questions or suggestions? Open an issue or reach out!

---

**Iridia Daily** - *Summarized Science Daily*
