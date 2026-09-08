import { CheckSquare, FileText, Paperclip } from 'lucide-react';
import type { RefObject } from 'react';

import {
  MeetingCreateActionButton,
  MeetingCreateChip,
} from './MeetingCreateChip';
import type { PickedDoc, PickedTask } from './MeetingCreateModal';

type LinkedWorkLabels = {
  addDoc: string;
  addFile: string;
  addTask: string;
  description: string;
  removeItem: (name: string) => string;
  title: string;
};

type LinkedWorkState = {
  pickedDocs: PickedDoc[];
  pickedFiles: File[];
  pickedTasks: PickedTask[];
};

type LinkedWorkHandlers = {
  onFileInputChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onOpenDocPicker: () => void;
  onOpenTaskPicker: () => void;
  onRemoveDoc: (docId: string) => void;
  onRemoveFile: (index: number) => void;
  onRemoveTask: (taskId: string) => void;
};

type MeetingCreateLinkedWorkSectionProps = {
  fileInputRef: RefObject<HTMLInputElement | null>;
  formatFileSize: (bytes: number) => string;
  handlers: LinkedWorkHandlers;
  labels: LinkedWorkLabels;
  state: LinkedWorkState;
};

function fileChipKey(file: File): string {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

export function MeetingCreateLinkedWorkSection({
  fileInputRef,
  formatFileSize,
  handlers,
  labels,
  state,
}: MeetingCreateLinkedWorkSectionProps) {
  const hasPickedItems =
    state.pickedTasks.length > 0 ||
    state.pickedDocs.length > 0 ||
    state.pickedFiles.length > 0;

  return (
    <div className="space-y-2">
      <label className="app-text-control-sm text-app-ink/70">
        {labels.title}
      </label>
      <p className="app-text-caption text-app-ink/40">{labels.description}</p>
      {hasPickedItems ? (
        <div className="flex flex-wrap gap-1.5">
          {state.pickedTasks.map((task) => (
            <MeetingCreateChip
              key={`task-${task.id}`}
              icon={<CheckSquare size={11} className="text-app-ink/40" />}
              onRemove={() => handlers.onRemoveTask(task.id)}
              removeLabel={labels.removeItem(task.title)}
            >
              {task.reference ? `${task.reference} · ` : ''}
              {task.title}
            </MeetingCreateChip>
          ))}
          {state.pickedDocs.map((doc) => (
            <MeetingCreateChip
              key={`doc-${doc.id}`}
              icon={<FileText size={11} className="text-app-ink/40" />}
              onRemove={() => handlers.onRemoveDoc(doc.id)}
              removeLabel={labels.removeItem(doc.title)}
            >
              {doc.title}
            </MeetingCreateChip>
          ))}
          {state.pickedFiles.map((file, index) => (
            <MeetingCreateChip
              key={fileChipKey(file)}
              icon={<Paperclip size={11} className="text-app-ink/40" />}
              meta={`(${formatFileSize(file.size)})`}
              onRemove={() => handlers.onRemoveFile(index)}
              removeLabel={labels.removeItem(file.name)}
            >
              {file.name}
            </MeetingCreateChip>
          ))}
        </div>
      ) : null}
      <div className="flex gap-2">
        <MeetingCreateActionButton
          onClick={handlers.onOpenTaskPicker}
          icon={<CheckSquare size={12} />}
        >
          {labels.addTask}
        </MeetingCreateActionButton>
        <MeetingCreateActionButton
          onClick={handlers.onOpenDocPicker}
          icon={<FileText size={12} />}
        >
          {labels.addDoc}
        </MeetingCreateActionButton>
        <MeetingCreateActionButton
          onClick={() => fileInputRef.current?.click()}
          icon={<Paperclip size={12} />}
        >
          {labels.addFile}
        </MeetingCreateActionButton>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          aria-label={labels.addFile}
          className="hidden"
          onChange={handlers.onFileInputChange}
        />
      </div>
    </div>
  );
}
