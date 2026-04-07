import { createReactBlockSpec } from '@blocknote/react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react';

const VARIANT_STYLES = {
  info: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', icon: Info, text: 'text-blue-400' },
  warning: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', icon: AlertTriangle, text: 'text-amber-400' },
  success: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', icon: CheckCircle2, text: 'text-emerald-400' },
  error: { bg: 'bg-red-500/10', border: 'border-red-500/30', icon: AlertCircle, text: 'text-red-400' },
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
      const variant = (props.block.props.variant as keyof typeof VARIANT_STYLES) || 'info';
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
