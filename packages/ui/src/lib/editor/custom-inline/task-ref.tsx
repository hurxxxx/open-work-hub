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
          className="inline-flex items-center gap-1 rounded bg-purple-500/20 px-1.5 py-0.5 text-xs font-medium text-purple-300 cursor-pointer hover:bg-purple-500/30 transition-colors"
          data-issue-id={props.inlineContent.props.issueId}
        >
          #{issueKey || title || 'Unknown'}
        </span>
      );
    },
  },
);
