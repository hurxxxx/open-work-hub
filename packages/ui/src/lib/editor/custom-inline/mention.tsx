import { createReactInlineContentSpec } from '@blocknote/react';

export const Mention = createReactInlineContentSpec(
  {
    type: 'mention' as const,
    propSchema: {
      userId: { default: '' },
      displayName: { default: '' },
    },
    content: 'none',
  },
  {
    render: (props) => (
      <span
        className="inline-flex items-center gap-1 rounded bg-blue-500/20 px-1.5 py-0.5 text-xs font-medium text-blue-300 cursor-default"
        data-user-id={props.inlineContent.props.userId}
      >
        @{props.inlineContent.props.displayName || 'Unknown'}
      </span>
    ),
  },
);
