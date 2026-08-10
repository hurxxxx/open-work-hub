import { createReactBlockSpec } from '@blocknote/react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react';

const VARIANT_STYLES = {
  info: {
    bg: 'bg-app-info/10',
    border: 'border-app-info/30',
    icon: Info,
    text: 'text-app-info-text',
  },
  warning: {
    bg: 'bg-ui-warning/10',
    border: 'border-ui-warning/30',
    icon: AlertTriangle,
    text: 'text-app-warning-text',
  },
  success: {
    bg: 'bg-ui-success/10',
    border: 'border-ui-success/30',
    icon: CheckCircle2,
    text: 'text-app-success-text',
  },
  error: {
    bg: 'bg-ui-danger/10',
    border: 'border-ui-danger/30',
    icon: AlertCircle,
    text: 'text-app-danger-text',
  },
} as const;

export const Callout = createReactBlockSpec(
  {
    type: 'callout' as const,
    propSchema: {
      variant: { default: 'info' as const },
    },
    content: 'inline',
  },
  {
    render: (props) => {
      const variant =
        (props.block.props.variant as keyof typeof VARIANT_STYLES) || 'info';
      const style = VARIANT_STYLES[variant] ?? VARIANT_STYLES.info;
      const IconComp = style.icon;

      return (
        <div
          className={`flex items-start gap-3 rounded-md border p-3 my-1 ${style.bg} ${style.border}`}
        >
          <IconComp size={18} className={`mt-0.5 shrink-0 ${style.text}`} />
          <div className="flex-1 min-w-0" ref={props.contentRef} />
        </div>
      );
    },
  },
);
