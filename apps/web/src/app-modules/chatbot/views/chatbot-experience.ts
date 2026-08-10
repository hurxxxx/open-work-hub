import type { ReactNode } from 'react';

import type { WorkspaceAppId } from '@/src/platform/workspaces/workspace-utils';
import type { ArtifactBuffer } from '../api/agent-events';

export interface ChatbotArtifactRenderContext {
  relatedArtifacts: readonly ArtifactBuffer[];
}

export interface ChatbotArtifactRenderer {
  type: string;
  preview?: (artifact: ArtifactBuffer) => string | null;
  render: (
    artifact: ArtifactBuffer,
    context: ChatbotArtifactRenderContext,
  ) => ReactNode;
}

export interface ChatbotConversationScopeBinding {
  ref: string;
  resourceId: string;
}

export type ChatbotExecutionMode = 'inline' | 'durable_background';

export interface ChatbotExperienceConfig {
  title?: string;
  routeAppId?: WorkspaceAppId;
  routePathSuffix?: string;
  conversationScope?: ChatbotConversationScopeBinding;
  sidebarEyebrow?: string;
  sidebarTitle?: string;
  emptyGreeting?: string;
  emptySubline?: string;
  artifactRenderers?: readonly ChatbotArtifactRenderer[];
  autoOpenArtifacts?: boolean;
  executionMode?: ChatbotExecutionMode;
  sourceArtifactTypes?: readonly string[];
}

export type ResolvedChatbotExperienceConfig = Required<
  Pick<
    ChatbotExperienceConfig,
    | 'routeAppId'
    | 'routePathSuffix'
    | 'sidebarEyebrow'
    | 'sidebarTitle'
    | 'title'
    | 'autoOpenArtifacts'
  >
> &
  Pick<
    ChatbotExperienceConfig,
    | 'artifactRenderers'
    | 'conversationScope'
    | 'emptyGreeting'
    | 'emptySubline'
    | 'executionMode'
    | 'sourceArtifactTypes'
  >;
