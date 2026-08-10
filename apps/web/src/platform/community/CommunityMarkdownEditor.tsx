import {
  type CSSProperties,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Crepe } from '@milkdown/crepe';
import { replaceAll } from '@milkdown/kit/utils';
import ReactMarkdown, {
  defaultUrlTransform,
  type Components,
} from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import remarkGfm from 'remark-gfm';

import { cn } from '@/src/lib/utils';

import './community-markdown-editor.css';

const REMARK_PLUGINS = [remarkGfm];
const REHYPE_PLUGINS = [rehypeHighlight];

type UploadFile = (file: File) => Promise<string>;
type ResolveFileUrl = (url: string) => Promise<string>;

export interface CommunityMarkdownEditorProps {
  ariaLabel: string;
  compact?: boolean;
  minHeight?: number;
  onChange: (value: string) => void;
  placeholder: string;
  resolveFileUrl?: ResolveFileUrl;
  uploadFile?: UploadFile;
  value: string;
}

export interface CommunityMarkdownViewerProps {
  className?: string;
  markdown: string;
  resolveFileUrl?: ResolveFileUrl;
}

export function CommunityMarkdownEditor({
  ariaLabel,
  compact = false,
  minHeight = compact ? 160 : 280,
  onChange,
  placeholder,
  resolveFileUrl,
  uploadFile,
  value,
}: CommunityMarkdownEditorProps) {
  const { t } = useTranslation('apps');
  const rootRef = useRef<HTMLDivElement | null>(null);
  const crepeRef = useRef<Crepe | null>(null);
  const lastMarkdownRef = useRef(value);
  const onChangeRef = useRef(onChange);
  const resolveFileUrlRef = useRef(resolveFileUrl);
  const uploadFileRef = useRef(uploadFile);
  const [editorError, setEditorError] = useState(false);

  const copy = useMemo(
    () => ({
      advanced: t('community.editor.advanced'),
      bold: t('community.editor.bold'),
      bulletList: t('community.editor.bulletList'),
      code: t('community.editor.code'),
      codeBlock: t('community.editor.codeBlock'),
      confirm: t('community.editor.confirm'),
      divider: t('community.editor.divider'),
      h1: t('community.editor.heading1'),
      h2: t('community.editor.heading2'),
      h3: t('community.editor.heading3'),
      h4: t('community.editor.heading4'),
      h5: t('community.editor.heading5'),
      h6: t('community.editor.heading6'),
      image: t('community.editor.image'),
      imageCaptionPlaceholder: t('community.editor.imageCaptionPlaceholder'),
      imageLinkPlaceholder: t('community.editor.imageLinkPlaceholder'),
      imageUploadFailed: t('community.editor.imageUploadFailed'),
      imageUploadUnavailable: t('community.editor.imageUploadUnavailable'),
      inlineCode: t('community.editor.inlineCode'),
      italic: t('community.editor.italic'),
      link: t('community.editor.link'),
      linkPlaceholder: t('community.editor.linkPlaceholder'),
      list: t('community.editor.list'),
      loadFailed: t('community.editor.loadFailed'),
      orderedList: t('community.editor.orderedList'),
      paragraph: t('community.editor.paragraph'),
      quote: t('community.editor.quote'),
      strikethrough: t('community.editor.strikethrough'),
      table: t('community.editor.table'),
      taskList: t('community.editor.taskList'),
      text: t('community.editor.text'),
      upload: t('community.editor.upload'),
      uploadFile: t('community.editor.uploadFile'),
    }),
    [t],
  );

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    resolveFileUrlRef.current = resolveFileUrl;
  }, [resolveFileUrl]);

  useEffect(() => {
    uploadFileRef.current = uploadFile;
  }, [uploadFile]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;

    let disposed = false;
    let controlObserver: MutationObserver | null = null;
    setEditorError(false);
    root.replaceChildren();

    const crepe = new Crepe({
      defaultValue: lastMarkdownRef.current,
      features: {
        [Crepe.Feature.Latex]: false,
        [Crepe.Feature.Toolbar]: false,
        [Crepe.Feature.TopBar]: true,
      },
      featureConfigs: {
        [Crepe.Feature.BlockEdit]: {
          advancedGroup: {
            codeBlock: { label: copy.code },
            image: { label: copy.image },
            label: copy.advanced,
            math: null,
            table: { label: copy.table },
          },
          listGroup: {
            bulletList: { label: copy.bulletList },
            label: copy.list,
            orderedList: { label: copy.orderedList },
            taskList: { label: copy.taskList },
          },
          textGroup: {
            divider: { label: copy.divider },
            h1: { label: copy.h1 },
            h2: { label: copy.h2 },
            h3: { label: copy.h3 },
            h4: { label: copy.h4 },
            h5: { label: copy.h5 },
            h6: { label: copy.h6 },
            label: copy.text,
            quote: { label: copy.quote },
            text: { label: copy.text },
          },
        },
        [Crepe.Feature.ImageBlock]: {
          blockCaptionPlaceholderText: copy.imageCaptionPlaceholder,
          blockConfirmButton: copy.confirm,
          blockOnUpload: uploadCommunityImage,
          blockUploadButton: copy.uploadFile,
          blockUploadPlaceholderText: copy.imageLinkPlaceholder,
          inlineConfirmButton: copy.confirm,
          inlineOnUpload: uploadCommunityImage,
          inlineUploadButton: copy.upload,
          inlineUploadPlaceholderText: copy.imageLinkPlaceholder,
          maxHeight: 720,
          maxWidth: 960,
          onUpload: uploadCommunityImage,
          proxyDomURL: resolveCommunityImageUrl,
        },
        [Crepe.Feature.LinkTooltip]: {
          inputPlaceholder: copy.linkPlaceholder,
        },
        [Crepe.Feature.Placeholder]: {
          mode: 'block',
          text: placeholder,
        },
        [Crepe.Feature.TopBar]: {
          headingOptions: [
            { label: copy.paragraph, level: null },
            { label: copy.h1, level: 1 },
            { label: copy.h2, level: 2 },
            { label: copy.h3, level: 3 },
            { label: copy.h4, level: 4 },
            { label: copy.h5, level: 5 },
            { label: copy.h6, level: 6 },
          ],
        },
      },
      root,
    });

    crepe.on((listener) => {
      listener.markdownUpdated((_, markdown) => {
        const normalizedMarkdown = normalizeCommunityMarkdown(markdown);
        lastMarkdownRef.current = normalizedMarkdown;
        onChangeRef.current(normalizedMarkdown);
      });
    });

    crepe
      .create()
      .then(() => {
        if (disposed) {
          void crepe.destroy();
          return;
        }
        crepeRef.current = crepe;
        labelCrepeControls(root, {
          toolbar: [
            copy.bold,
            copy.italic,
            copy.strikethrough,
            copy.inlineCode,
            copy.link,
          ],
          topBar: [
            copy.bold,
            copy.italic,
            copy.strikethrough,
            copy.inlineCode,
            copy.bulletList,
            copy.orderedList,
            copy.taskList,
            copy.link,
            copy.image,
            copy.table,
            copy.codeBlock,
            copy.quote,
            copy.divider,
          ],
        });
        controlObserver = new MutationObserver(() => {
          labelCrepeControls(root, {
            toolbar: [
              copy.bold,
              copy.italic,
              copy.strikethrough,
              copy.inlineCode,
              copy.link,
            ],
            topBar: [
              copy.bold,
              copy.italic,
              copy.strikethrough,
              copy.inlineCode,
              copy.bulletList,
              copy.orderedList,
              copy.taskList,
              copy.link,
              copy.image,
              copy.table,
              copy.codeBlock,
              copy.quote,
              copy.divider,
            ],
          });
        });
        controlObserver.observe(root, { childList: true, subtree: true });
      })
      .catch(() => {
        if (disposed) return;
        setEditorError(true);
      });

    return () => {
      disposed = true;
      controlObserver?.disconnect();
      if (crepeRef.current === crepe) {
        crepeRef.current = null;
      }
      void crepe.destroy().catch(() => undefined);
    };

    async function uploadCommunityImage(file: File): Promise<string> {
      const upload = uploadFileRef.current;
      if (!upload) {
        throw new Error(copy.imageUploadUnavailable);
      }
      try {
        return await upload(file);
      } catch {
        throw new Error(copy.imageUploadFailed);
      }
    }

    async function resolveCommunityImageUrl(url: string): Promise<string> {
      if (!url.startsWith('media:')) return url;
      const resolve = resolveFileUrlRef.current;
      if (!resolve) return url;
      try {
        return await resolve(url);
      } catch {
        return url;
      }
    }
  }, [copy, placeholder]);

  useEffect(() => {
    const crepe = crepeRef.current;
    if (!crepe || value === lastMarkdownRef.current) return;
    lastMarkdownRef.current = value;
    crepe.editor.action(replaceAll(value, true));
  }, [value]);

  const style = {
    '--community-editor-min-height': `${minHeight}px`,
  } as CSSProperties;

  return (
    <div
      className="community-markdown-editor"
      data-compact={compact ? 'true' : 'false'}
      style={style}
    >
      <div
        aria-label={ariaLabel}
        className={cn(editorError && 'hidden')}
        ref={rootRef}
        role="group"
      />
      {editorError ? (
        <div className="grid gap-1">
          <p className="app-text-caption text-app-ink/55">{copy.loadFailed}</p>
          <textarea
            aria-label={ariaLabel}
            className="min-h-28 w-full resize-y rounded-md border border-app-border bg-app-bg px-3 py-2 app-text-body-sm text-app-ink outline-none focus:border-app-accent"
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            value={value}
          />
        </div>
      ) : null}
    </div>
  );
}

export function CommunityMarkdownViewer({
  className,
  markdown,
  resolveFileUrl,
}: CommunityMarkdownViewerProps) {
  const components = useMemo<Components>(
    () => ({
      a({ children, href }) {
        if (!href) return <span>{children}</span>;
        return (
          <a
            href={href}
            rel="noreferrer"
            target={href.startsWith('#') ? undefined : '_blank'}
          >
            {children}
          </a>
        );
      },
      img({ alt, src }) {
        return (
          <ResolvedMarkdownImage
            alt={alt ?? ''}
            resolveFileUrl={resolveFileUrl}
            src={src ? String(src) : ''}
          />
        );
      },
    }),
    [resolveFileUrl],
  );
  const normalizedMarkdown = useMemo(
    () => normalizeCommunityMarkdown(markdown),
    [markdown],
  );

  return (
    <div
      className={cn(
        'community-markdown-viewer app-markdown prose prose-sm max-w-none dark:prose-invert',
        className,
      )}
    >
      <ReactMarkdown
        components={components}
        rehypePlugins={REHYPE_PLUGINS}
        remarkPlugins={REMARK_PLUGINS}
        urlTransform={communityUrlTransform}
      >
        {normalizedMarkdown}
      </ReactMarkdown>
    </div>
  );
}

export function stripCommunityMarkdownPreview(markdown: string): string {
  return normalizeCommunityMarkdown(markdown)
    .replace(/!\[[^\]]*]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^[\s>*+-]+/gm, '')
    .replace(/[`*_~|]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export function normalizeCommunityMarkdown(markdown: string): string {
  return markdown.replace(/<br\s*\/?>/gi, '\n');
}

function ResolvedMarkdownImage({
  alt,
  resolveFileUrl,
  src,
}: {
  alt: string;
  resolveFileUrl?: ResolveFileUrl;
  src: string;
}) {
  const [resolvedSrc, setResolvedSrc] = useState(src);

  useEffect(() => {
    let cancelled = false;
    setResolvedSrc(src);

    if (!src.startsWith('media:') || !resolveFileUrl) {
      return () => {
        cancelled = true;
      };
    }

    resolveFileUrl(src)
      .then((url) => {
        if (!cancelled) setResolvedSrc(url);
      })
      .catch(() => {
        if (!cancelled) setResolvedSrc(src);
      });

    return () => {
      cancelled = true;
    };
  }, [resolveFileUrl, src]);

  if (!resolvedSrc) return null;
  return <img alt={alt} loading="lazy" src={resolvedSrc} />;
}

function communityUrlTransform(value: string): string {
  return value.startsWith('media:') ? value : defaultUrlTransform(value);
}

function labelCrepeControls(
  root: HTMLElement,
  labels: { toolbar: string[]; topBar: string[] },
) {
  root
    .querySelectorAll<HTMLElement>('.milkdown-top-bar .top-bar-item')
    .forEach((control, index) => {
      const label = labels.topBar[index];
      if (!label) return;
      control.setAttribute('aria-label', label);
      control.setAttribute('title', label);
    });

  root
    .querySelectorAll<HTMLElement>('.milkdown-toolbar .toolbar-item')
    .forEach((control, index) => {
      const label = labels.toolbar[index];
      if (!label) return;
      control.setAttribute('aria-label', label);
      control.setAttribute('title', label);
    });
}
