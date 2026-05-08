# Iridia Daily

Iridia Daily is a serverless newsletter service that delivers daily scientific research insights — sourced directly from recently published PubMed papers — to subscribers' inboxes. It is live at [iridia-daily.com](https://iridia-daily.com).

---

## Features

- **Real research**: Pulls from PubMed papers published within the last week
- **AI-powered summaries**: Uses Claude Sonnet 4.6 via AWS Bedrock to transform complex research into accessible, engaging insights
- **Topic subscriptions**: Subscribers choose from seven research topics — neuroscience, space, biology, environment, physics, medicine, and technology
- **Double opt-in**: Subscription confirmation via HMAC-signed email links
- **Preference management**: Subscribers can update their topic preferences or unsubscribe at any time
- **Web archive**: A browsable archive of past newsletters, filterable by topic, hosted on the live site
- **Monitoring**: CloudWatch alarms with SNS-based alerting for newsletter and subscription errors
- **Fully serverless**: No servers to manage; scales automatically

---

## Architecture

```
EventBridge (Daily at 7am EST)
    |
    v
NewsletterFunction (Lambda)
    |
    |---> PubMed API          (fetch recent papers by topic)
    |---> AWS Bedrock         (generate accessible research insight)
    |---> SES Contact List    (send to opted-in subscribers)
    |---> S3 Archive Bucket   (store newsletter for web archive)

API Gateway
    |
    |---> /subscribe          (POST — initiate double opt-in)
    |---> /confirm            (GET  — verify HMAC token, activate subscription)
    |---> /unsubscribe        (GET  — verified unsubscribe via HMAC token)
    |---> /preferences        (GET/POST — view and update topic preferences)
    |---> /archive/{proxy+}   (GET  — serve archived newsletters)
    |---> /health             (GET  — service health check)
```

**Tech stack:**

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Infrastructure | AWS SAM (IaC) |
| AI model | Anthropic Claude Sonnet 4.6 (via AWS Bedrock) |
| Email | AWS SES (contact lists, bulk send, templating) |
| Archive storage | AWS S3 + SQLite |
| Secrets | AWS Secrets Manager |
| Scheduling | AWS EventBridge |
| Observability | AWS CloudWatch + SNS |
| Frontend | Vanilla HTML/CSS/JS, hosted on S3 |

---

## How It Works

### Newsletter pipeline

The newsletter runs once daily on an EventBridge schedule. Rather than sending one fixed email to all subscribers, the handler first reads every subscriber's topic preferences from the SES contact list and groups subscribers by their unique preference combinations. This means subscribers who share the same set of topics receive an identical email, while those with different preferences receive a tailored one — all without redundant AI calls.

For each unique subscriber group, the handler issues a single combined PubMed search query covering all needed topics at once, then categorizes the returned papers using a weighted keyword-scoring algorithm. Title matches are weighted four times higher than abstract matches, and exact word-boundary hits score higher than partial matches, so papers land in the most relevant topic bucket. Papers are then distributed evenly across topics using a round-robin pass, so no single topic dominates a newsletter edition.

All paper summaries are generated in a single Bedrock call, keeping latency and cost low. The prompt instructs Claude to write short, witty two-to-three sentence summaries (capped at 280 characters each) that are accurate to the research but conversational in tone. Once summaries are ready, the handler dispatches emails via SES bulk send in batches of 50, embedding per-subscriber HMAC-signed unsubscribe and preferences links directly into each message.

### Subscription and token security

Subscriptions follow a double opt-in flow. When a visitor submits the form on the website, the API validates their email and selected topics, then sends a confirmation email containing a signed link. Clicking that link calls the `/confirm` endpoint, which verifies the token and activates the subscription.

All action links — confirm, unsubscribe, and preferences — are secured with HMAC-SHA256 tokens generated from a secret stored in AWS Secrets Manager. Confirmation tokens embed an expiry timestamp and are only valid for 24 hours. Unsubscribe tokens have no expiry, so subscribers can always opt out. Token verification uses constant-time comparison to prevent timing attacks.

Topic preferences are stored directly in SES as `TopicPreferences` on each contact, so there is no separate database for subscriber state.

### Archive storage

After each newsletter run, the handler appends the day's papers and their summaries to a SQLite database file stored in S3. The archive Lambda function downloads this file to its `/tmp` directory on cold start and caches it for the rest of the day, so repeated archive requests within the same day do not re-download the file. The database uses FTS5 (SQLite's built-in full-text search extension) for fast keyword search and standard indexes on `date` and `topic` for filtering and pagination. This approach costs a fraction of a cent per month compared to an equivalent DynamoDB setup.

### Website

The website is a static HTML/CSS/JS application hosted on S3. It loads the archive from the `/archive` API endpoint and renders research papers in a filterable grid by topic. A subscribe modal collects the visitor's email and topic preferences, then calls the `/subscribe` endpoint to begin the double opt-in flow.

---

## Development

### Running tests

```bash
cd tests
./run_tests.sh
```

### Local invocation (requires Docker)

```bash
sam build
sam local invoke NewsletterFunction
```

### Viewing logs

```bash
sam logs --tail --name NewsletterFunction
```

---

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for full setup and deployment instructions.

---

## Troubleshooting

**No emails received?**
- Make sure you clicked the confirmation link in the email sent after subscribing — without that step, the subscription is not activated
- Check your spam or junk folder; transactional email from a new domain occasionally ends up there
- If you confirmed but still receive nothing, wait until the next scheduled send at 7am EST
- Check Lambda logs in CloudWatch for errors on the newsletter function

**Confirmation link says it has expired?**
- Confirmation links are only valid for 24 hours. Return to [iridia-daily.com](https://iridia-daily.com) and subscribe again — a fresh link will be sent immediately

**Subscribed but not receiving the right topics?**
- Use the preferences link at the bottom of any newsletter email to review and update your topic selections
- Changes take effect on the next newsletter run

**Unsubscribe link not working?**
- Unsubscribe links do not expire, but if the link appears broken, copy the full URL from the email and paste it directly into your browser
- If the problem persists, reply to any newsletter email and request removal

**Archive not loading on the website?**
- The archive is populated after the first newsletter run; if the service was just deployed, it may be empty until the next scheduled send
- Open the browser developer console and check for API errors — a CORS or authorization error suggests the API URL in `website/config.js` may be incorrect

**Tests failing locally?**
- Ensure you are running Python 3.12 and have installed test dependencies: `pip install -r src/requirements-test.txt`
- Some tests mock AWS clients; if they fail with credential errors, check that `moto` is installed and that no real AWS calls are being made unexpectedly
- Run `cd tests && ./run_tests.sh` from the project root, not from within the `tests/` directory, as the script sets paths relative to the project root

---

## Planned Improvements

**Infrastructure**

- **CI/CD pipeline**: Automate build, test, and deployment on merge to eliminate the current manual `sam build && sam deploy` workflow
- **CloudFront distribution**: Add a CloudFront layer in front of the S3-hosted website for CDN caching, TLS termination at the edge, and consistent custom domain handling without exposing the S3 bucket URL directly

**Website**

- **Footer pages**: The About, Privacy Policy, and Terms links in the footer are currently placeholders; these pages need to be written and wired up
- **Technology topic filter**: The `technology` topic is fully supported in the backend and newsletter pipeline but is missing from the website's filter bar — the two need to be brought into sync

**Developer experience**

- **PR template**: Standardize contribution and change documentation to reduce review overhead

**Observability**

- **Email engagement metrics**: There is currently no tracking for open rates or click-through rates; adding SES click and open tracking would surface whether summaries are resonating and which topics drive the most engagement

---

## License

See [LICENSE](LICENSE).

---

## Acknowledgments

- [PubMed / NCBI](https://pubmed.ncbi.nlm.nih.gov/) for free, open access to research paper metadata
- [Anthropic](https://www.anthropic.com/) for Claude, accessed via AWS Bedrock
- [AWS SAM](https://aws.amazon.com/serverless/sam/) for making serverless infrastructure straightforward to define and deploy
