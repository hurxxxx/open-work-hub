import { Button } from '@open-work-hub/ui';
import { Check, Circle, ListTodo, LoaderCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { active, record, string, type Detail, type Model } from './api';
import { statusCopy, type Translate } from './i18n';

export type Execution = {
  model: string | null;
  effort: string | null;
  permissions: 'ask' | 'yolo';
};

const preferredModel = 'gpt-5.6-sol';
const preferredEffort = 'medium';

function effortFor(model: Model) {
  if (model.model === preferredModel && model.efforts.includes(preferredEffort))
    return preferredEffort;
  if (model.efforts.includes(model.default_effort)) return model.default_effort;
  return model.efforts[0] ?? null;
}

export function resolveExecution(value: Execution, models: Model[]): Execution {
  const selected = models.find((row) => row.model === value.model);
  if (selected) {
    const effort =
      value.effort && selected.efforts.includes(value.effort)
        ? value.effort
        : effortFor(selected);
    return effort === value.effort ? value : { ...value, effort };
  }
  const fallback =
    models.find((row) => row.model === preferredModel) ??
    models.find((row) => row.is_default) ??
    models[0];
  return fallback
    ? { ...value, model: fallback.model, effort: effortFor(fallback) }
    : value;
}

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
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (disabled) setExpanded(false);
  }, [disabled]);
  return (
    <fieldset className="execution-settings" disabled={disabled}>
      <legend>{t('Next execution')}</legend>
      <div className="execution-settings-summary">
        <span>
          {t('Model and reasoning')}
          <strong>
            {model?.name ?? value.model ?? t('Loading model catalog…')}
            {value.effort ? ` · ${value.effort}` : ''}
          </strong>
        </span>
        <Button
          variant="ghost"
          aria-expanded={expanded}
          disabled={disabled}
          onClick={() => setExpanded((current) => !current)}
        >
          {t(expanded ? 'Hide settings' : 'Change settings')}
        </Button>
      </div>
      {expanded && (
        <div className="execution-model-controls">
          <label>
            {t('Model')}
            <select
              value={value.model ?? ''}
              disabled={!models.length}
              onChange={(event) => {
                const next = models.find(
                  (row) => row.model === event.target.value,
                );
                onChange({
                  ...value,
                  model: next?.model ?? null,
                  effort: next ? effortFor(next) : null,
                });
              }}
            >
              {!models.length && (
                <option value="">{t('Loading model catalog…')}</option>
              )}
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
              {value.effort && !model?.efforts.includes(value.effort) && (
                <option value={value.effort}>{value.effort}</option>
              )}
              {model?.efforts.map((effort) => (
                <option key={effort} value={effort}>
                  {effort}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      <label className="execution-permissions">
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
        <Button
          className="execution-model-retry"
          variant="ghost"
          onClick={onRetry}
        >
          {t('Reload models')}
        </Button>
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
  const currentCommandText =
    active(task) && currentCommand ? string(currentCommand.command) : '';
  return (
    <div
      className="execution-status"
      role="region"
      aria-label={t('Execution status')}
    >
      <div className="execution-status-heading" role="status">
        <strong>
          <span className={`dot ${active(task) ? 'online pulse' : ''}`} />{' '}
          {t(statusCopy(task.status))}
        </strong>
        <span>
          {t(
            task.stage === 'implement' || task.stage === 'review'
              ? 'Execute'
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
      <div className="execution-activity">
        {steps.length > 0 ? (
          <details className="execution-progress">
            <summary>
              <ListTodo size={14} />
              <span>
                {t('Execution steps')} · {complete}/{steps.length}
              </span>
              {currentCommandText && (
                <code className="current-command">{currentCommandText}</code>
              )}
            </summary>
            <div className="execution-progress-panel">
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
            </div>
          </details>
        ) : currentCommandText ? (
          <code className="current-command">{currentCommandText}</code>
        ) : (
          <span className="execution-activity-placeholder" aria-hidden="true">
            &nbsp;
          </span>
        )}
      </div>
    </div>
  );
}
