import { BlockNoteEditor, BlockNoteSchema, defaultBlockSpecs, defaultInlineContentSpecs } from '@blocknote/core';
import { blocksToYDoc, yDocToBlocks } from '@blocknote/core/yjs';
import { createReactBlockSpec, createReactInlineContentSpec } from '@blocknote/react';
import * as Y from 'yjs';

function createSchema() {
  const Callout = createReactBlockSpec(
    {
      type: 'callout',
      propSchema: {
        variant: { default: 'info' },
      },
      content: 'inline',
    },
    {
      render: () => null,
    },
  );

  const Divider = createReactBlockSpec(
    {
      type: 'divider',
      propSchema: {},
      content: 'none',
    },
    {
      render: () => null,
    },
  );

  const Mention = createReactInlineContentSpec(
    {
      type: 'mention',
      propSchema: {
        userId: { default: '' },
        displayName: { default: '' },
      },
      content: 'none',
    },
    {
      render: () => null,
    },
  );

  const TaskRef = createReactInlineContentSpec(
    {
      type: 'taskRef',
      propSchema: {
        issueId: { default: '' },
        issueKey: { default: '' },
        title: { default: '' },
      },
      content: 'none',
    },
    {
      render: () => null,
    },
  );

  return BlockNoteSchema.create({
    blockSpecs: {
      ...defaultBlockSpecs,
      callout: Callout(),
      divider: Divider(),
    },
    inlineContentSpecs: {
      ...defaultInlineContentSpecs,
      mention: Mention,
      taskRef: TaskRef,
    },
  });
}

function createEditor() {
  return BlockNoteEditor.create({
    schema: createSchema(),
  });
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

async function main() {
  const mode = process.argv[2];
  if (!mode || !['encode', 'decode'].includes(mode)) {
    throw new Error('Expected mode: encode | decode');
  }

  const raw = await readStdin();
  const payload = raw ? JSON.parse(raw) : {};
  const editor = createEditor();

  if (mode === 'encode') {
    const blocks = Array.isArray(payload.blocks) ? payload.blocks : [];
    const ydoc = blocksToYDoc(editor, blocks);
    const yjsState = Buffer.from(Y.encodeStateAsUpdate(ydoc)).toString('base64');
    process.stdout.write(JSON.stringify({ yjs_state: yjsState }));
    return;
  }

  const ydoc = new Y.Doc();
  const base64Value = typeof payload.yjs_state === 'string' ? payload.yjs_state : '';
  if (base64Value) {
    Y.applyUpdate(ydoc, Buffer.from(base64Value, 'base64'));
  }
  const blocks = yDocToBlocks(editor, ydoc);
  process.stdout.write(JSON.stringify({ blocks }));
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exit(1);
});
