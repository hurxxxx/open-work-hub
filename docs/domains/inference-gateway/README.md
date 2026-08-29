# Inference Gateway Domain

API/worker call embedding, rerank, OCR, and ASR backends through approved gateway adapters. The RAG
provider factory owns embedding/rerank/OCR composition; the core ASR adapter owns speech requests.

- Deployment chooses actual models/hardware.
- App code must not assume hostnames, servers, or devices.
- LLM routing/audit/usage/cost belongs to [AI Gateway](../ai/gateway.md).
