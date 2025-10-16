# SciBits 🔬

> **Bite-sized science, fresh from the lab**

SciBits is a serverless notification service that delivers fascinating scientific facts from recently published research papers directly to your inbox. Built on AWS using Lambda, Bedrock (Claude), and SNS.

## ✨ Features

- 📄 **Real Research**: Pulls from actual PubMed papers published in the last week
- 🤖 **AI-Powered**: Uses Claude 3.5 Sonnet to transform complex research into accessible facts
- 📧 **Email Delivery**: Daily notifications via AWS SNS
- ⚡ **Serverless**: Completely serverless architecture - costs pennies per month
- 🔗 **Source Links**: Every fact includes a link to the original research paper
- 📅 **Scheduled**: Runs automatically on your preferred schedule
- 🎯 **Scalable**: Broadcast same fact to unlimited subscribers

## 🏗️ Architecture

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

## 💰 Cost

Running SciBits costs approximately **$0.12/month** for 100 subscribers:

| Service | Monthly Cost |
|---------|-------------|
| Lambda | Free (within free tier) |
| Bedrock (Claude) | ~$0.09 |
| SNS | ~$0.015 |
| EventBridge | Free |
| CloudWatch Logs | ~$0.01 |

## 🚀 Quick Start

### Prerequisites

- AWS Account with Bedrock access enabled
- AWS CLI configured
- AWS SAM CLI installed
- Python 3.12
- Docker (optional, for local testing)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/scibits.git
cd scibits
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
# - Stack Name: scibits
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

## 🛠️ Configuration

### Change Schedule

Edit `template.yaml` to change when facts are sent:

```yaml
Schedule: cron(0 13 * * ? *)  # Daily at 8am EST
```

**Common schedules:**
- `cron(0 13 * * ? *)` - Daily at 8am EST (1pm UTC)
- `cron(0 20 * * ? *)` - Daily at 3pm EST (8pm UTC)  
- `cron(0 14 ? * MON *)` - Every Monday at 9am EST
- `cron(0 12 ? * MON-FRI *)` - Weekdays at 7am EST

### Customize Topics

Edit `src/lambda_function.py` to change research fields:

```python
# Current (broad science)
query = urllib.parse.quote(f"(biology[MeSH] OR physics OR neuroscience OR astronomy) AND {date_range}[PDAT]")

# Focus on specific field (e.g., space science)
query = urllib.parse.quote(f"(astrophysics OR cosmology OR astronomy) AND {date_range}[PDAT]")
```

### Add More Subscribers

```bash
# Get your SNS topic ARN
TOPIC_ARN=$(aws cloudformation describe-stacks \
  --stack-name scibits \
  --query 'Stacks[0].Outputs[?OutputKey==`SNSTopicArn`].OutputValue' \
  --output text)

# Subscribe new email
aws sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol email \
  --notification-endpoint friend@example.com
```

## 📁 Project Structure

```
scibits/
├── template.yaml              # SAM infrastructure definition
├── src/
│   ├── lambda_function.py     # Main Lambda function
│   └── requirements.txt       # Python dependencies
├── .gitignore
└── README.md
```

## 🔧 Development

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

```bash
# After making changes
sam build && sam deploy
```

### View Logs

```bash
# Real-time logs
sam logs --tail --name FactGeneratorFunction

# Recent logs
sam logs --name FactGeneratorFunction --start-time '10min ago'
```

## 🐛 Troubleshooting

### No email received?
1. Check you confirmed the SNS subscription
2. Check spam folder
3. View Lambda logs: `sam logs --tail --name FactGeneratorFunction`

### Bedrock "Access Denied" error?
1. Enable Claude 3.5 Sonnet in AWS Console → Bedrock → Model Access
2. Ensure you're in the same region (us-east-1)
3. Verify IAM permissions in template.yaml

### "Rate exceeded" error?
Wait 1 minute between deployments. CloudFormation has rate limits.

## 🎨 Customization Ideas

- **Implement CI/CD** so that much of the building/testing/deploying can be automated
- **Web archive** hosted on S3 + CloudFront

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **PubMed/NCBI** for providing free access to research papers
- **Anthropic** for Claude AI via AWS Bedrock
- **AWS SAM** for making serverless deployment simple

## 📮 Contact

Have questions or suggestions? Open an issue or reach out!

---

**SciBits** - *Science in digestible bits* 🔬✨
