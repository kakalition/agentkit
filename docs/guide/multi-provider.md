# Multiple Model Providers

## Introduction

`MODEL_NAME` names a model as `provider:model` and agentkit builds the matching
PydanticAI provider. A bare name (no `:`) defaults to `openai`.

```bash
MODEL_NAME=anthropic:claude-3-7-sonnet
ANTHROPIC_API_KEY=sk-ant-...
```

## Built-in providers

| Prefix | Env | Notes |
| --- | --- | --- |
| `openai` | `OPENAI_API_KEY`, `OPENAI_BASE_URL` | timeout/retries from `MODEL_TIMEOUT`/`MODEL_RETRIES` |
| `openai-compatible` | `OPENAI_BASE_URL`, `OPENAI_API_KEY` (optional) | any OpenAI-compatible endpoint |
| `anthropic` | `ANTHROPIC_API_KEY` | |
| `google` | `GOOGLE_API_KEY` | |
| `groq` | `GROQ_API_KEY` | needs `agentkit[groq]` |
| `mistral` | `MISTRAL_API_KEY` | needs `agentkit[mistral]` |
| `ollama` | `OLLAMA_BASE_URL` | local models, no key |
| `bedrock` | `AWS_*`, `BEDROCK_REGION`, `AWS_PROFILE` | needs `agentkit[bedrock]`; standard AWS credential chain |
| `openrouter` | `OPENROUTER_API_KEY` | model names are `openrouter:<upstream>/<model>`, e.g. `openrouter:openai/gpt-4o` |
| `azure` | `AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_API_VERSION` | Azure OpenAI; uses the core `openai` package |
| `litellm` | underlying provider env vars | needs `agentkit[litellm]`; `litellm:<provider>/<model>` |
| `deepseek` | `DEEPSEEK_API_KEY` | |
| `together` | `TOGETHER_API_KEY` | |
| `fireworks` | `FIREWORKS_API_KEY` | |
| `cerebras` | `CEREBRAS_API_KEY` | |
| `vercel` | `VERCEL_API_KEY` | Vercel AI Gateway |

```bash
MODEL_NAME=bedrock:us.anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_REGION=us-east-1
```

A missing key raises a `ConfigurationError` naming the env var; a missing optional
package raises it naming the `agentkit[<extra>]` to install; an unknown prefix
names the supported set.

## Resolving programmatically

```python
from agentkit import resolve_model, register_model_provider, supported_prefixes
from agentkit.config import get_settings

model = resolve_model("anthropic:claude-3-7-sonnet", get_settings())
print(supported_prefixes())
```

`build_model(settings)` is a thin wrapper over `resolve_model`.

## Your own provider

```python
register_model_provider("my-provider", lambda model, settings: MyModel(model))
model = resolve_model("my-provider:foo", settings)
```

## Routing and cost

`ModelRouter` routes by the full `provider:model` string, so you can mix
providers in one app (cheap model for triage, a strong one for the final
answer). Token cost is priced with `genai-prices`; `UsageRecord.cost_usd` records
it per turn.
