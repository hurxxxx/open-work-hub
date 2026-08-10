import { MarkdownContent } from './MarkdownContent';

export interface DocumentArtifactProps {
  content: string;
}

export function DocumentArtifact({ content }: DocumentArtifactProps) {
  return <MarkdownContent content={content} unwrapMarkdownFence />;
}
