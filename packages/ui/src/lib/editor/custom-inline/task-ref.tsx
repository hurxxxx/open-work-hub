import { createReactInlineContentSpec } from '@blocknote/react';

export const TaskRef = createReactInlineContentSpec(
  {
    type: 'taskRef' as const,
    propSchema: {
      issueId: { default: '' },
      issueKey: { default: '' },
      title: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => {
      const { issueKey, title } = props.inlineContent.props;
      return (
        <span
          className="inline-flex items-center gap-1 rounded bg-ui-accent/10 px-1.5 py-0.5 text-[length:var(--ui-text-caption)] font-medium text-ui-accent cursor-pointer hover:bg-ui-accent/15 transition-colors"
          data-issue-id={props.inlineContent.props.issueId}
        >
          #{issueKey || title || 'Unknown'}
        </span>
      );
    },
  },
);
