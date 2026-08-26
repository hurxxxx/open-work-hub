# Inference Gateway Domain

API/worker call embedding, rerank, parser, and ASR backends through one HTTP contract.

- Deployment chooses actual models/hardware.
- App code must not assume hostnames, servers, or devices.
- LLM routing/audit/usage/cost belongs to [AI Gateway](../ai/gateway.md).
