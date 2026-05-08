# Deployment Guide

This guide covers first-time setup and ongoing deployment of the Iridia Daily service.

---

## Prerequisites

- AWS account with Bedrock model access enabled for Claude Sonnet 4.6
- AWS CLI configured with appropriate credentials
- AWS SAM CLI installed
- Python 3.12
- A verified sender domain in AWS SES

---

## First-Time Deployment

### 1. Clone the repository

```bash
git clone https://github.com/erhardt-ren/iridia-daily-service.git
cd iridia-daily-service
```

### 2. Enable Bedrock model access

In the AWS Console, navigate to **Bedrock > Model Access** and enable **Claude Sonnet 4.6**. Wait for "Access granted" before proceeding — deploying before access is granted will cause the newsletter function to fail on first run.

### 3. Build and deploy

```bash
sam build
sam deploy --guided
```

Follow the interactive prompts. Key parameters:

| Parameter | Description | Example |
|---|---|---|
| `SenderEmail` | Verified SES sender address | `research@yourdomain.com` |
| `ContactListName` | SES contact list name for subscribers | `iridia-daily-subscribers` |
| `AlertEmail` | Email address for CloudWatch alarm notifications | `alerts@yourdomain.com` |
| `StageName` | Deployment stage (lowercase only) | `prod` |

SAM will save these values to `samconfig.toml` so subsequent deployments do not require the `--guided` flag.

### 4. Verify your sender domain

Before any emails can be sent, your sender domain must be verified in SES. For production use, you must also request that AWS move your account out of SES sandbox mode. While in sandbox, SES can only send to verified recipient addresses.

To verify a domain, go to **SES > Verified identities > Create identity** and follow the DNS verification steps for your domain.

### 5. Deploy the website

The website is a static application hosted on S3. After the backend stack is deployed, update `website/config.js` with the API Gateway URL from the SAM outputs, then upload the contents of the `website/` directory to your S3 static hosting bucket.

The API URL is available in the CloudFormation stack outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name <your-stack-name> \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text
```

---

## Deploying Updates

```bash
sam build && sam deploy
```

SAM will use the parameter values saved in `samconfig.toml` from the initial guided deployment.

---

## Configuration

### Change the newsletter schedule

The newsletter runs daily at 7am EST by default. To change this, edit the `Schedule` property of `NewsletterFunction` in `template.yaml`:

```yaml
Schedule: cron(0 11 * * ? *)  # 7am EST (UTC-4) / 11:00 UTC
```

Cron expressions in AWS EventBridge use UTC. The format is:
`cron(minutes hours day-of-month month day-of-week year)`

### Add or remove research topics

Topics are defined in two places that must stay in sync:

1. The SES contact list topics in `template.yaml` under `NewsletterContactList`
2. The `CATEGORY_MAPPING` dictionary in `src/iridia_daily/config.py`, which maps each topic name to the PubMed keywords used to find relevant papers

To add a topic, add an entry to both locations and redeploy.

### Stack parameters

All configurable parameters are defined in the `Parameters` section of `template.yaml` and can be overridden at deploy time:

```bash
sam deploy --parameter-overrides StageName=staging AlertEmail=me@example.com
```

---

## Useful Commands

```bash
# View all stack outputs (API URLs, bucket names, etc.)
aws cloudformation describe-stacks --stack-name <stack-name> --query "Stacks[0].Outputs"

# Manually trigger a newsletter run
aws lambda invoke --function-name iridia-daily-newsletter response.json && cat response.json

# Tail live logs for any function
sam logs --tail --name NewsletterFunction

# Run tests locally
cd tests && ./run_tests.sh

# Local function invocation (requires Docker)
sam build && sam local invoke NewsletterFunction
```

---

## Troubleshooting

**Bedrock "Access Denied" error?**
- Go to AWS Console > Bedrock > Model Access and confirm Claude Sonnet 4.6 shows "Access granted"
- Confirm the `BEDROCK_MODEL_ID` environment variable in `template.yaml` uses the cross-region inference profile ID: `us.anthropic.claude-sonnet-4-6`, not the base foundation model ID
- Verify the Lambda execution role in `template.yaml` has `bedrock:InvokeModel` permission against that inference profile ARN — the region must match your deployment region

**CloudFormation "Rate exceeded" error?**
- CloudFormation has API rate limits that can be hit when deploying frequently. Wait one minute and re-run `sam deploy`

**SES emails not sending?**
- If your AWS account is still in SES sandbox mode, you can only send to verified email addresses. Request production access in the SES console under **Account dashboard > Request production access**
- Verify your sender domain under **SES > Verified identities**; an unverified domain will cause all sends to fail silently

**SAM build fails with dependency errors?**
- Ensure you are building with Python 3.12: `python3 --version`
- If `sam build` fails to resolve packages, try `sam build --use-container` to build inside a Lambda-compatible Docker image

**Stack stuck in `UPDATE_ROLLBACK_FAILED`?**
- This typically means a resource deletion failed mid-rollback. In the CloudFormation console, use **Continue update rollback** and skip the offending resource if it no longer exists
