import { jsonHeaders } from '@/src/platform/api/client';

export interface DocumentProviderHealth {
  provider_name: string;
  ready: boolean;
}

export interface DocumentVisionWorkload {
  workload_id: string;
  owner_domain: string;
  app_ids: string[];
  effective_route: 'local' | 'external';
  provider_id: string | null;
  model_key: string | null;
  max_output_tokens: number;
  ready: boolean;
  readiness_code: string | null;
}

export interface AdminDocumentProcessingSnapshot {
  configuration_scope: 'api_environment';
  health_scope: 'api_process';
  worker_health_available: boolean;
  enabled: boolean;
  ready: boolean;
  query_timeout_ms: number;
  providers: DocumentProviderHealth[];
  ocr: {
    provider: string;
    endpoint_configured: boolean;
    credential_configured: boolean;
    force_ocr: boolean;
    engine: string;
    languages: string[];
    minimum_text_chars: number;
  };
  vision: {
    enabled: boolean;
    timeout_seconds: number;
    max_pages: number;
    dpi: number;
    max_new_tokens: number;
    workloads: DocumentVisionWorkload[];
  };
  embedding: {
    provider: string;
    endpoint_configured: boolean;
    credential_configured: boolean;
    model: string;
    revision: string | null;
    batch_size: number;
  };
  rerank: {
    provider: string;
    endpoint_configured: boolean;
    credential_configured: boolean;
    model: string;
    revision: string | null;
    batch_size: number;
    candidate_limit: number;
  };
  vector_index: {
    provider: string;
    endpoint_configured: boolean;
    credential_configured: boolean;
    collection_prefix: string;
    active_collection: string | null;
  };
  keyword_index: {
    provider: string;
    endpoint_configured: boolean;
    index_prefix: string;
  };
  chunking: {
    strategy: string;
    target_chars: number;
    hard_max_chars: number;
    overlap_chars: number;
    minimum_chars: number;
    index_text_max_chars: number;
  };
  legacy_issues: {
    attachment_index_enabled: boolean;
    always_use_vision: boolean;
    vision_max_pages: number;
    maximum_chunks: number;
    semantic_search_enabled: boolean;
    write_embeddings_enabled: boolean;
    embedding_dimensions: number;
    vector_store: 'postgresql_pgvector';
  };
}

export async function getAdminDocumentProcessingSnapshot(
  token: string,
): Promise<AdminDocumentProcessingSnapshot> {
  const response = await fetch('/api/v1/admin/document-processing', {
    cache: 'no-store',
    headers: jsonHeaders(token),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      payload && typeof payload.detail === 'string'
        ? payload.detail
        : 'Document processing status request failed.',
    );
  }
  return payload as AdminDocumentProcessingSnapshot;
}
