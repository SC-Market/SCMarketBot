# SCMarketBot
This is the repository that hosts the official Discord bot for [SC Market](https://sc-market.space).

## Features
- Discord bot for order management and fulfillment
- **NEW**: AWS SQS integration for asynchronous event processing
- Queue-based event processing for better scalability

## Local Development
This project requires Python 3.12. You can install requirements with
```shell
python -m pip install -r requirements.txt
```

## Configuration
The bot now uses AWS SQS queues for all event processing. See [SQS Configuration Guide](SQS_CONFIGURATION.md) for detailed setup instructions.

### Quick Start
1. Set your Discord bot token: `DISCORD_API_KEY=your_token`
2. Configure AWS credentials: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
3. Set queue URLs from your deployed CDK stack:
   - `DISCORD_QUEUE_URL=https://sqs.us-east-2.amazonaws.com/ACCOUNT/DiscordQueuesStack-discord-queue`
   - `BACKEND_QUEUE_URL=https://sqs.us-east-2.amazonaws.com/ACCOUNT/DiscordQueuesStack-backend-queue`
4. Enable SQS mode: Set `ENABLE_SQS=true` and `ENABLE_DISCORD_QUEUE=true`

The bot can be launched from the Docker configuration in [the backend](https://github.com/SC-Market/sc-market-backend).