# Using Amazon Bedrock with SpeakLoop

SpeakLoop's simulator asks a planner what to do next. Set `SPEAKLOOP_LLM=bedrock` to use the
**Amazon Bedrock Converse API** with tool use (`speakloop/agent.py::bedrock_step`):

1. The simulator lists the MCP tools and reads the Agent Skill over MCP.
2. `/agent/step` maps each MCP tool to a Bedrock `toolSpec` (`inputSchema.json` = the MCP JSON Schema) and sends
   the conversation as Converse `messages`, with tool calls as `toolUse` and MCP results as `toolResult` blocks.
3. The Agent Skill text is the `system` prompt, plus runtime context (learner id, today's date, simulator state).
4. If the model returns `toolUse`, the browser executes it against the MCP server; otherwise its text is spoken.

## Setup
```bash
pip install boto3
export SPEAKLOOP_LLM=bedrock AWS_REGION=us-east-1 BEDROCK_MODEL_ID=us.amazon.nova-lite-v1:0
# credentials: AWS_PROFILE / SSO / env vars — standard boto3 chain; never commit keys
python -m speakloop.server
```
Enable model access for the chosen model in the Bedrock console first. Any Converse-compatible model with tool
use works (Amazon Nova, Anthropic Claude on Bedrock, …).

Minimal IAM policy:
```json
{ "Version": "2012-10-17", "Statement": [ { "Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": "*" } ] }
```

## Cost notes
No AWS resources are created by this repo. Each learner turn is one short Converse call (≤400 output tokens).
Tests use a stubbed Bedrock client, so CI never calls AWS.
