import { createReactBlockSpec } from '@blocknote/react';

export const Divider = createReactBlockSpec(
  {
    type: 'divider' as const,
    propSchema: {},
    content: 'none',
  },
  {
    render: () => (
      <div className="py-2">
        <hr className="border-t border-neutral-700" />
      </div>
    ),
  },
);
