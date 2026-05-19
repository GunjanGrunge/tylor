# Claude Platform on AWS Setup Guide

You've successfully configured agent101 to use Claude Platform on AWS. Here's what was set up:

## ✓ Completed Setup

### 1. AWS Credentials
- **Status**: Active ✓
- **Profile**: `default` (from `~/.aws/credentials`)
- **User**: `bedrock_agent` in account `751289209169`
- **Region**: `us-east-1`

### 2. Environment Variables Configured

Added to `server/.env`:
```bash
CLAUDE_CODE_USE_ANTHROPIC_AWS=1
ANTHROPIC_AWS_WORKSPACE_ID=wrkspc_01C19h6yMnj1V4X6Uo3VUrjj
ANTHROPIC_AWS_BASE_URL=https://aws-external-anthropic.us-east-1.api.aws
AWS_PROFILE=default
AWS_REGION=us-east-1
```

### 3. Authentication Method
- **Type**: AWS SigV4 (recommended for teams)
- **Credentials location**: `~/.aws/credentials`
- **Workspace**: `wrkspc_01C19h6yMnj1V4X6Uo3VUrjj`

## 🚀 Next Steps

### Option A: Run Claude Code CLI with AWS

```bash
# 1. Source the setup script
source .aws-setup.sh

# 2. Verify Claude Code can see AWS
code /status

# 3. Start your project
code "your question here"
```

### Option B: Run agent101 FastMCP Server

```bash
# 1. Navigate to server directory
cd server

# 2. Load AWS environment
source ../.aws-setup.sh

# 3. Install dependencies (if not already done)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Start the FastMCP server
python3 -m server.main
```

### Option C: Use Agent SDK

Your FastMCP server can now use Claude Platform on AWS by reading these environment variables:

```python
import os
from anthropic import Anthropic

# These are automatically read from .env
client = Anthropic(
    api_key=os.getenv("ANTHROPIC_AWS_API_KEY") or None,  # Falls back to AWS SigV4
    base_url="https://aws-external-anthropic.us-east-1.api.aws"
)
```

## 📋 Troubleshooting

### If you see "403 Forbidden" or "AccessDenied"
- Check IAM permissions for your user in AWS Console
- Verify role has `aws-external-anthropic:InvokeModel` permission
- Check that workspace ID is correct

### If Claude Code is still hitting `api.anthropic.com`
- Verify `CLAUDE_CODE_USE_ANTHROPIC_AWS=1` is set (not 0 or blank)
- Check that `CLAUDE_CODE_USE_BEDROCK` and `CLAUDE_CODE_USE_FOUNDRY` are not set
- Run `code /status` to confirm resolved provider

### If credentials expire
- Re-run the setup script or manually re-export variables
- Credentials from `~/.aws/credentials` should work without refresh needed

## 📚 Additional Resources

- [Claude Platform on AWS docs](https://platform.claude.com/docs/en/build-with-claude/claude-platform-on-aws)
- [IAM action reference](https://platform.claude.com/docs/en/api/claude-platform-on-aws-iam-actions)
- [Claude models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

## 🔐 Security Notes

- Your API key is in `server/.env` (Git ignored)
- AWS credentials come from `~/.aws/credentials`
- Keep workspace ID confidential
- Rotate API keys periodically if using that method instead of SigV4
