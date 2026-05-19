#!/bin/bash
# Claude Platform on AWS Setup for agent101

# AWS Credentials Configuration
# Using existing credentials in ~/.aws/credentials
export AWS_PROFILE=default
export AWS_REGION=us-east-1

# Claude Platform on AWS Configuration
export CLAUDE_CODE_USE_ANTHROPIC_AWS=1
export ANTHROPIC_AWS_WORKSPACE_ID=wrkspc_01C19h6yMnj1V4X6Uo3VUrjj
export ANTHROPIC_AWS_BASE_URL=https://aws-external-anthropic.us-east-1.api.aws

# Model versions (optional - uses latest if not set)
# export ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-4-7
# export ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-4-6
# export ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-haiku-4-5

# Refresh credentials if they expire
export AWS_AUTH_REFRESH="aws sso login --profile ${AWS_PROFILE}"

echo "✓ Claude Platform on AWS environment configured"
echo "  Workspace ID: $ANTHROPIC_AWS_WORKSPACE_ID"
echo "  Region: $AWS_REGION"
echo "  Auth method: AWS credentials (SigV4)"
