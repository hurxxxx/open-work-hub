import { Button } from '@open-work-hub/ui';
import { Check, Circle, LoaderCircle } from 'lucide-react';
import { active, record, string, type Detail, type Model } from './api';
import { statusCopy, type Translate } from './i18n';

export type Execution = {
  model: string | null;
  effort: string | null;
  permissions: 'ask' | 'yolo';
};

export function ExecutionSettings({
  models,
  value,
  onChange,
  disabled,
  implementation,
  failed,
  onRetry,
  t,
}: {
  models: Model[];
  value: Execution;
  onChange: (value: Execution) => void;
  disabled: boolean;
  implementation: boolean;
  failed: boolean;
  onRetry: () => void;
  t: Translate;
}) {
  const model = models.find((row) => row.model === value.model);
  return (
    <fieldset className="execution-settings" disabled={disabled}>
      <legend>{t('Next execution')}</legend>
      <label>
        {t('Model')}
        <select
          value={value.model ?? ''}
          onChange={(event) =>
            onChange({
              ...value,
              model: event.target.value || null,
              effort: null,
            })
          }
        >
          <option value="">{t('Codex default')}</option>
          {value.model && !model && (
            <option value={value.model}>{value.model}</option>
          )}
          {models.map((row) => (
            <option key={row.model} value={row.model}>
              {row.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('Reasoning effort')}
        <select
          value={value.effort ?? ''}
          disabled={!model}
          onChange={(event) =>
            onChange({ ...value, effort: event.target.value || null })
          }
        >
          <option value="">{t('Default')}</option>
          {model?.efforts.map((effort) => (
            <option key={effort} value={effort}>
              {effort}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('Permissions')}
        <select
          value={implementation ? value.permissions : 'read-only'}
          disabled={!implementation}
          onChange={(event) =>
            onChange({
              ...value,
              permissions: event.target.value as Execution['permissions'],
            })
          }
        >
          {!implementation && (
            <option value="read-only">{t('Read-only')}</option>
          )}
          <option value="ask">{t('Ask when needed')}</option>
          <option value="yolo">{t('YOLO · Full access')}</option>
        </select>
      </label>
      {failed && (
        <Button variant="ghost" onClick={onRetry}>
          {t('Reload models')}
        </Button>
      )}
      {implementation && value.permissions === 'yolo' && (
        <p className="danger">
          {t('YOLO runs commands without approval or sandbox restrictions.')}
        </p>
      )}
    </fieldset>
  );
}

export function ExecutionStatus({
  task,
  connected,
  t,
}: {
  task: Detail;
  connected: boolean;
  t: Translate;
}) {
  const progress = record(task.progress);
  const steps = Array.isArray(progress.steps) ? progress.steps.map(record) : [];
  const complete = steps.filter((step) => step.status === 'completed').length;
  const currentCommand = [...task.items]
    .reverse()
    .find(
      (item) =>
        item.type === 'commandExecution' &&
        item.turn_id === task.turn_id &&
        item.status === 'inProgress',
    );
  return (
    <div className="execution-status" aria-label={t('Execution status')}>
      <div className="execution-status-heading" role="status">
        <strong>
          <span className={`dot ${active(task) ? 'online pulse' : ''}`} />{' '}
          {t(statusCopy(task.status))}
        </strong>
        <span>
          {t(
            task.stage === 'implement' || task.stage === 'review'
              ? 'Implement'
              : task.stage === 'chat'
                ? 'General chat'
                : task.stage === 'requirements'
                  ? 'Requirements'
                  : 'Plan',
          )}
        </span>
        {task.model && (
          <span>
            {task.model}
            {task.effort ? ` · ${task.effort}` : ''}
          </span>
        )}
        <span className={task.permissions === 'yolo' ? 'danger' : ''}>
          {t(
            task.permissions === 'yolo'
              ? 'YOLO · Full access'
              : task.permissions === 'ask'
                ? 'Ask when needed'
                : 'Read-only',
          )}
        </span>
      </div>
      <p className="muted">
        {t(
          connected
            ? 'Work continues on the server when you leave this page.'
            : 'Reconnecting live updates. Leaving this page does not stop the server task.',
        )}
      </p>
      {active(task) && currentCommand && (
        <code className="current-command">
          {string(currentCommand.command)}
        </code>
      )}
      {steps.length > 0 && (
        <details open={active(task)}>
          <summary>
            {t('Execution steps')} · {complete}/{steps.length}
          </summary>
          {string(progress.explanation) && (
            <p>{string(progress.explanation)}</p>
          )}
          <ol>
            {steps.map((step, index) => (
              <li key={index} data-state={string(step.status)}>
                {step.status === 'completed' ? (
                  <Check size={14} />
                ) : step.status === 'inProgress' ? (
                  <LoaderCircle size={14} />
                ) : (
                  <Circle size={14} />
                )}
                <span>{string(step.step)}</span>
                <small>
                  {t(
                    step.status === 'completed'
                      ? 'Completed'
                      : step.status === 'inProgress'
                        ? 'In progress'
                        : 'Pending',
                  )}
                </small>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
