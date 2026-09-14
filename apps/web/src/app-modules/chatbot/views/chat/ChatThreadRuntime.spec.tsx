import {
  AssistantRuntimeProvider,
  ThreadPrimitive,
  useExternalStoreRuntime,
  useAuiState,
  type ThreadMessageLike,
} from '@assistant-ui/react';
import { render, screen, waitFor } from '@testing-library/react';
import { expect, it } from 'vitest';

const convertMessage = (message: ThreadMessageLike) => message;
const onNew = async () => undefined;
function ProbeMessage() {
  const id = useAuiState((state) => state.message.id);
  return <span>{id}</span>;
}
const components = { Message: ProbeMessage };
function Probe({ messages }: { messages: ThreadMessageLike[] }) {
  const runtime = useExternalStoreRuntime({ messages, convertMessage, onNew });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Messages components={components} />
    </AssistantRuntimeProvider>
  );
}
it('updates a message id using only the documented external store API', async () => {
  const { rerender } = render(
    <Probe messages={[{ id: 'first', role: 'assistant', content: 'A' }]} />,
  );
  expect(screen.getByText('first')).toBeTruthy();
  rerender(
    <Probe messages={[{ id: 'second', role: 'assistant', content: 'B' }]} />,
  );
  await waitFor(() => expect(screen.getByText('second')).toBeTruthy());
});
