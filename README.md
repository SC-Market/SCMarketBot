# SCMarketBot
This is the repository that hosts the official Discord bot for [SC Market](https://sc-market.space).

## Features
- Discord bot for order management and fulfillment
- Web server for receiving events from the main website
- **NEW**: AWS SQS integration for asynchronous event processing
- Support for both synchronous and queued processing modes

## Local Development
This project requires Python 3.12. You can install requirements with
```shell
python -m pip install -r requirements.txt
```

## Configuration
The bot supports both traditional web server mode and AWS SQS queue mode. See [SQS Configuration Guide](SQS_CONFIGURATION.md) for detailed setup instructions.

### Quick Start
1. Set your Discord bot token: `DISCORD_API_KEY=your_token`
2. Configure AWS credentials: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
3. Set queue URLs from your deployed CDK stack:
   - `DISCORD_QUEUE_URL=https://sqs.us-east-2.amazonaws.com/ACCOUNT/DiscordQueuesStack-discord-queue`
   - `BACKEND_QUEUE_URL=https://sqs.us-east-2.amazonaws.com/ACCOUNT/DiscordQueuesStack-backend-queue`
4. Choose your mode:
   - **Web Server Mode**: Set `ENABLE_WEB_SERVER=true` and `ENABLE_SQS=false`
   - **SQS Mode**: Set `ENABLE_SQS=true` and `ENABLE_DISCORD_QUEUE=true`

The bot can be launched from the Docker configuration in [the backend](https://github.com/SC-Market/sc-market-backend).