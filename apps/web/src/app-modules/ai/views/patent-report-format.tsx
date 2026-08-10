import { Fragment, useMemo } from 'react';
import type { ReactNode } from 'react';

import { cn } from '@/src/lib/utils';

// Renders an AI 특허 보고서 (plain text with section markers) into readable
// cards. Ported from the legacy Flask tool's `_pfFormatResult` (C:\server
// templates/sections/patent_file.html) so the new ai-do output matches it:
// [섹션] headers, 청구항, verdict badges (높음/보통/낮음), numbered subsections,
// bullet lists, 예: blocks, and inline **bold** / `code`.

type Tone = 'pos' | 'neg' | 'neu';

type Block =
  | { k: 'section'; sub: boolean; text: string }
  | { k: 'claim'; num: string; text: string }
  | { k: 'verdict'; tone: Tone; label: string; value: string; body: string }
  | { k: 'sub'; num: string; circle: boolean; title: string; desc: string }
  | { k: 'li'; level: 1 | 2; header: boolean; text: string }
  | { k: 'ex'; text: string }
  | { k: 'p'; text: string };

const VERDICT_WORD =
  '((?:매우\\s*)?(?:높음|보통|낮음|있음|없음|충분|부족|양호|미흡))';
// Korean markers in the LLM report text — parsing patterns and fixed labels,
// not translatable UI copy (the report body is generated in Korean).
const CLAIM_RE = /^청구항\s*(\d+)\.\s*(.+)$/;
const EXAMPLE_LEAD_RE = /^예\s*[:)]/;
const CLAIM_LABEL = '청구항';
const DEFAULT_VERDICT_LABEL = '평가 결과';

function parseReport(text: string): Block[] {
  const blocks: Block[] = [];
  if (!text) return blocks;
  const lines = text.replace(/\r\n/g, '\n').split('\n');

  for (const raw of lines) {
    const trimmed = raw.trim();
    if (!trimmed) continue;
    const leadSpaces = (raw.match(/^[\t ]*/)?.[0] ?? '').replace(
      /\t/g,
      '    ',
    ).length;

    // [섹션 헤더] (들여쓰기 ≥2 이면 서브블록)
    let m = trimmed.match(/^\[([^\]]+)\](?:\s*[-—–]\s*.+)?$/);
    if (m) {
      blocks.push({ k: 'section', sub: leadSpaces >= 2, text: m[1] });
      continue;
    }

    // 마크다운 헤더 #, ##, ###
    m = trimmed.match(/^(#{1,4})\s+(.+?)\s*#*\s*$/);
    if (m) {
      blocks.push({ k: 'section', sub: m[1].length >= 3, text: m[2] });
      continue;
    }

    // 청구항 N. 본문
    m = trimmed.match(CLAIM_RE);
    if (m) {
      blocks.push({ k: 'claim', num: m[1], text: m[2] });
      continue;
    }

    // 평가 결과 (높음/보통/낮음 …) → 배지 카드
    {
      let verdict: string | null = null;
      let prefix = '';
      let body = '';
      let mm = trimmed.match(new RegExp('^' + VERDICT_WORD + '$'));
      if (mm) verdict = mm[1];
      if (!verdict) {
        // "출원 가능성: 보통" 라벨형. verdict 단어 뒤에 붙는 부연 절
        // ("... (선행기술 조사 결과에 따라 높음으로 상향 가능)")까지 body 로
        // 함께 잡아, 설명이 평문으로 떨어지지 않고 배지 아래에 따라붙게 한다.
        // 단어 경계(공백/괄호)가 있어야만 매칭해 "보통상" 같은 오인식을 막는다.
        mm = trimmed.match(
          new RegExp(
            '^(.{1,30}?)\\s*[:：]\\s*' +
              VERDICT_WORD +
              '(\\s+.*|\\s*[（(].*)?$',
          ),
        );
        if (mm) {
          prefix = mm[1].trim();
          verdict = mm[2];
          body = (mm[3] ?? '').trim();
        }
      }
      if (!verdict) {
        mm = trimmed.match(
          new RegExp('^' + VERDICT_WORD + '\\s*[.。,，]\\s*(.+)$'),
        );
        if (mm) {
          verdict = mm[1];
          body = mm[2].trim();
        }
      }
      if (verdict) {
        const positive = /(매우\s*)?(높음|있음|충분|양호)$/.test(verdict);
        const negative = /(매우\s*)?(낮음|없음|부족|미흡)$/.test(verdict);
        const tone: Tone = positive ? 'pos' : negative ? 'neg' : 'neu';
        blocks.push({
          k: 'verdict',
          tone,
          label: prefix || DEFAULT_VERDICT_LABEL,
          value: verdict,
          body,
        });
        continue;
      }
    }

    // 원 번호 ①②③ → 부제목
    m = trimmed.match(/^([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])\s+(.+)$/);
    if (m) {
      const full = m[2];
      const dash = full.match(/^(.+?)\s+[-—–]\s+(.+)$/);
      blocks.push({
        k: 'sub',
        num: m[1],
        circle: true,
        title: dash ? dash[1] : full,
        desc: dash ? dash[2] : '',
      });
      continue;
    }

    // 숫자) 또는 숫자. 부제목
    m = trimmed.match(/^(\d+)[).]\s+(.+)$/);
    if (m) {
      const full = m[2];
      const dash = full.match(/^(.+?)\s+[-—–]\s+(.+)$/);
      blocks.push({
        k: 'sub',
        num: m[1],
        circle: false,
        title: dash ? dash[1] : full,
        desc: dash ? dash[2] : '',
      });
      continue;
    }

    // 불릿 (들여쓰기로 깊이 판정)
    m = raw.match(/^(\s*)[*\-•]\s+(.+)$/);
    if (m) {
      const indent = m[1].replace(/\t/g, '    ').length;
      const level: 1 | 2 = indent >= 4 ? 2 : 1;
      const content = m[2].trim();
      const header = /:$/.test(content) && !EXAMPLE_LEAD_RE.test(content);
      blocks.push({ k: 'li', level, header, text: content });
      continue;
    }

    // 예: / 예) 인용 블록
    if (EXAMPLE_LEAD_RE.test(trimmed)) {
      blocks.push({ k: 'ex', text: trimmed });
      continue;
    }

    blocks.push({ k: 'p', text: trimmed });
  }

  return blocks;
}

const INLINE_RE = /\*\*([^*\n]+?)\*\*|__([^_\n]+?)__|`([^`\n]+?)`/g;

// Inline **bold** / __bold__ / `code` → React nodes.
function renderInline(text: string): ReactNode {
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  INLINE_RE.lastIndex = 0;
  while ((m = INLINE_RE.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const bold = m[1] ?? m[2];
    if (bold != null) {
      nodes.push(
        <strong key={key++} className="font-bold text-app-ink">
          {bold}
        </strong>,
      );
    } else if (m[3] != null) {
      nodes.push(
        <code
          key={key++}
          className="rounded bg-app-surface-hover px-1 py-0.5 font-mono text-[0.92em] text-app-ink"
        >
          {m[3]}
        </code>,
      );
    }
    last = INLINE_RE.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const VERDICT_STYLE: Record<Tone, { icon: string; text: string; box: string }> =
  {
    pos: {
      icon: '🟢',
      text: 'text-app-success',
      box: 'border-emerald-500 bg-app-success/10',
    },
    neg: {
      icon: '🔴',
      text: 'text-app-danger',
      box: 'border-red-500 bg-app-danger/10',
    },
    neu: {
      icon: '🟠',
      text: 'text-app-warning',
      box: 'border-amber-500 bg-app-warning/10',
    },
  };

function renderBlock(block: Block, index: number): ReactNode {
  switch (block.k) {
    case 'section':
      return block.sub ? (
        <div
          key={index}
          className="mb-1.5 mt-4 rounded-r-md border-l-[3px] border-app-border-strong bg-app-surface-hover px-2.5 py-1.5 app-text-body-sm font-bold text-app-ink"
        >
          {renderInline(block.text)}
        </div>
      ) : (
        <div
          key={index}
          className="mb-3 mt-5 rounded-r-lg border-l-4 border-app-accent bg-app-surface-sidebar px-3.5 py-2.5 app-text-body font-bold tracking-tight text-app-accent"
        >
          {renderInline(block.text)}
        </div>
      );
    case 'claim':
      return (
        <div
          key={index}
          className="my-2 rounded-r-md border-l-[3px] border-app-accent bg-app-surface-sidebar px-3 py-2 app-text-body-sm leading-relaxed"
        >
          <span className="mr-2 inline-block min-w-[3.5rem] font-bold text-app-accent">
            {CLAIM_LABEL} {block.num}
          </span>
          <span className="text-app-ink">{renderInline(block.text)}</span>
        </div>
      );
    case 'verdict': {
      const style = VERDICT_STYLE[block.tone];
      return (
        <Fragment key={index}>
          <div
            className={cn(
              'mt-3.5 flex items-center gap-3 rounded-t-lg border-b-[3px] px-4 py-3.5',
              style.box,
            )}
          >
            <div className="text-2xl leading-none">{style.icon}</div>
            <div>
              <div className="text-[12px] font-semibold uppercase tracking-wide text-app-ink/55">
                {renderInline(block.label)}
              </div>
              <div
                className={cn(
                  'text-xl font-extrabold leading-tight',
                  style.text,
                )}
              >
                {renderInline(block.value)}
              </div>
            </div>
          </div>
          {block.body ? (
            <p className="mb-2 mt-2 app-text-body-sm leading-relaxed text-app-ink/80">
              {renderInline(block.body)}
            </p>
          ) : null}
        </Fragment>
      );
    }
    case 'sub':
      return (
        <div
          key={index}
          className="mb-2 mt-4 flex items-baseline gap-2.5 border-b border-dashed border-app-border py-1.5"
        >
          <span
            className={cn(
              'shrink-0',
              block.circle
                ? 'text-lg text-app-accent'
                : 'flex size-[22px] items-center justify-center rounded-full bg-app-accent text-[11px] font-extrabold text-app-accent-fg',
            )}
          >
            {block.num}
          </span>
          <span className="min-w-0 flex-1 break-words app-text-body-sm font-bold text-app-ink">
            {renderInline(block.title)}
          </span>
          {block.desc ? (
            <span className="shrink-0 app-text-micro text-app-ink/55">
              {renderInline(block.desc)}
            </span>
          ) : null}
        </div>
      );
    case 'li':
      return (
        <div
          key={index}
          className={cn(
            'flex gap-2 py-0.5 app-text-body-sm leading-relaxed',
            block.level === 2 && 'pl-5',
          )}
        >
          <span
            className={cn(
              'shrink-0',
              block.level === 2 ? 'text-app-ink/55' : 'font-bold text-app-accent',
            )}
          >
            {block.level === 2 ? '▸' : '▪'}
          </span>
          <span
            className={cn(
              'min-w-0',
              block.header ? 'font-bold text-app-ink' : 'text-app-ink/90',
            )}
          >
            {renderInline(block.text)}
          </span>
        </div>
      );
    case 'ex':
      return (
        <div
          key={index}
          className="my-1.5 ml-5 rounded-r-md border-l-[3px] border-app-border-strong bg-app-surface-hover px-2.5 py-1.5 app-text-micro leading-relaxed text-app-ink/70"
        >
          {renderInline(block.text)}
        </div>
      );
    case 'p':
      return (
        <p
          key={index}
          className="my-2 app-text-body-sm leading-relaxed text-app-ink/80"
        >
          {renderInline(block.text)}
        </p>
      );
  }
}

export function ReportContent({ text }: { text: string }) {
  const blocks = useMemo(() => parseReport(text), [text]);
  return (
    <div className="text-app-ink/90 [&>*:first-child]:mt-0">
      {blocks.map((block, index) => renderBlock(block, index))}
    </div>
  );
}

// Plain-text copy: drop markdown markers (matches the legacy 복사 behaviour).
export function stripReportMarkdown(text: string): string {
  return String(text || '')
    .replace(/\*\*([^*\n]+?)\*\*/g, '$1')
    .replace(/__([^_\n]+?)__/g, '$1')
    .replace(/`([^`\n]+?)`/g, '$1')
    .replace(/^#{1,4}\s+/gm, '');
}

// ── Standalone HTML export (서식 보존) ──────────────────────────────────────
function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function inlineHtml(s: string): string {
  return escapeHtml(s)
    .replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_\n]+?)__/g, '<strong>$1</strong>')
    .replace(/`([^`\n]+?)`/g, '<code class="pf-code">$1</code>');
}

const VERDICT_HTML: Record<Tone, { icon: string; color: string; bg: string }> =
  {
    pos: { icon: '🟢', color: '#2f9e44', bg: 'rgba(47,158,68,.10)' },
    neg: { icon: '🔴', color: '#c92a2a', bg: 'rgba(201,42,42,.10)' },
    neu: { icon: '🟠', color: '#e67700', bg: 'rgba(230,119,0,.10)' },
  };

function blocksToHtml(blocks: Block[]): string {
  const out: string[] = [];
  let listLevel = 0;
  const closeLists = () => {
    while (listLevel > 0) {
      out.push('</ul>');
      listLevel -= 1;
    }
  };

  for (const block of blocks) {
    if (block.k !== 'li') closeLists();
    switch (block.k) {
      case 'section':
        out.push(
          `<div class="${block.sub ? 'pf-subblock' : 'pf-section'}">${inlineHtml(block.text)}</div>`,
        );
        break;
      case 'claim':
        out.push(
          `<div class="pf-claim"><span class="pf-claim-num">${CLAIM_LABEL} ${escapeHtml(block.num)}</span><span class="pf-claim-text">${inlineHtml(block.text)}</span></div>`,
        );
        break;
      case 'verdict': {
        const style = VERDICT_HTML[block.tone];
        out.push(
          `<div class="pf-verdict-card" style="background:${style.bg};border-bottom:3px solid ${style.color};"><div class="pf-verdict-card-icon">${style.icon}</div><div><div class="pf-verdict-card-label">${inlineHtml(block.label)}</div><div class="pf-verdict-card-value" style="color:${style.color};">${inlineHtml(block.value)}</div></div></div>`,
        );
        if (block.body) {
          out.push(
            `<p class="pf-p" style="margin-top:8px;">${inlineHtml(block.body)}</p>`,
          );
        }
        break;
      }
      case 'sub': {
        const numCls = block.circle ? 'pf-num pf-num-circle' : 'pf-num';
        const desc = block.desc
          ? `<span class="pf-subdesc">${inlineHtml(block.desc)}</span>`
          : '';
        out.push(
          `<div class="pf-subsection"><span class="${numCls}">${escapeHtml(block.num)}</span><span class="pf-subtitle">${inlineHtml(block.title)}</span>${desc}</div>`,
        );
        break;
      }
      case 'li': {
        while (listLevel < block.level) {
          out.push(`<ul class="pf-list pf-list-${listLevel + 1}">`);
          listLevel += 1;
        }
        while (listLevel > block.level) {
          out.push('</ul>');
          listLevel -= 1;
        }
        out.push(
          `<li class="${block.header ? 'pf-bullet-header' : ''}">${inlineHtml(block.text)}</li>`,
        );
        break;
      }
      case 'ex':
        out.push(`<div class="pf-example">${inlineHtml(block.text)}</div>`);
        break;
      case 'p':
        out.push(`<p class="pf-p">${inlineHtml(block.text)}</p>`);
        break;
    }
  }
  closeLists();
  return `<div class="pf-formatted">${out.join('\n')}</div>`;
}

// Exported standalone document strings (Korean is the document's own content,
// not app UI). Held as constants so they read as data, not display copy.
const EXPORT_FONT = "'Pretendard','Noto Sans KR','맑은 고딕',sans-serif";
const EXPORT_SYSTEM_LABEL = '두원공조 · AI 특허 작성';
const EXPORT_DATE_LABEL = '작성일';
// prettier-ignore
const EXPORT_FOOTER = '두원공조 기술연구소 — AI 특허 작성 시스템에서 생성된 보고서입니다.';

const EXPORT_CSS = `
  :root {
    --text-primary:#1f2937; --text-secondary:#374151; --text-muted:#6b7280;
    --accent:#748ffc; --border:#e5e7eb; --bg-card:#ffffff; --bg-card2:#f9fafb;
    --input-bg:#f3f4f6; --font:${EXPORT_FONT};
  }
  *{box-sizing:border-box;}
  body{font-family:var(--font);max-width:960px;margin:40px auto;padding:30px 40px;color:var(--text-primary);background:#fff;line-height:1.75;font-size:13.5px;}
  .report-header{border-bottom:3px solid var(--accent);padding-bottom:16px;margin-bottom:28px;}
  .report-system{font-size:12px;color:var(--text-muted);letter-spacing:.5px;text-transform:uppercase;}
  .report-title{font-size:24px;font-weight:800;color:var(--text-primary);margin:4px 0 0;}
  .report-meta{font-size:11.5px;color:var(--text-muted);margin-top:6px;}
  .report-content{font-size:13px;line-height:1.85;}
  .report-content > *:first-child{margin-top:0;}
  .report-footer{margin-top:36px;padding-top:12px;border-top:1px solid var(--border);font-size:10.5px;color:var(--text-muted);text-align:center;}
  .pf-formatted{font-size:13px;line-height:1.8;color:var(--text-primary);}
  .pf-section{font-size:15px;font-weight:800;color:var(--accent);background:var(--bg-card2);border-left:4px solid var(--accent);padding:10px 14px;margin:20px 0 12px;border-radius:0 8px 8px 0;letter-spacing:.3px;}
  .pf-subblock{font-size:13px;font-weight:700;color:var(--text-primary);padding:5px 10px;margin:16px 0 6px;background:rgba(0,0,0,.025);border-left:3px solid var(--text-muted);border-radius:0 6px 6px 0;}
  .pf-subsection{display:flex;align-items:baseline;gap:10px;margin:18px 0 8px;padding:6px 0;border-bottom:1px dashed var(--border);}
  .pf-subsection .pf-num{display:inline-flex;align-items:center;justify-content:center;background:var(--accent);color:#fff;border-radius:50%;width:22px;height:22px;font-size:12px;font-weight:800;flex-shrink:0;}
  .pf-subsection .pf-num-circle{background:transparent;color:var(--accent);width:auto;height:auto;font-size:18px;}
  .pf-subsection .pf-subtitle{flex:1 1 0;min-width:0;word-break:break-word;overflow-wrap:anywhere;font-size:13.5px;font-weight:700;color:var(--text-primary);line-height:1.6;}
  .pf-subsection .pf-subdesc{flex-shrink:0;font-size:12px;font-weight:400;color:var(--text-muted);margin-left:4px;}
  .pf-formatted .pf-p{margin:8px 0;color:var(--text-secondary);line-height:1.85;}
  .pf-formatted ul.pf-list{margin:8px 0;padding:0 0 0 4px;list-style:none;}
  .pf-formatted ul.pf-list-2{padding-left:20px;margin:4px 0;}
  .pf-formatted ul.pf-list li{position:relative;padding:3px 0 3px 18px;color:var(--text-primary);line-height:1.7;}
  .pf-formatted ul.pf-list-1 > li::before{content:"▪";position:absolute;left:0;top:3px;color:var(--accent);font-weight:700;font-size:12px;}
  .pf-formatted ul.pf-list-2 > li::before{content:"▸";position:absolute;left:0;top:3px;color:var(--text-muted);font-weight:700;}
  .pf-formatted li.pf-bullet-header{font-weight:700;color:var(--text-primary);margin-top:6px;}
  .pf-formatted .pf-example{margin:6px 0 6px 22px;padding:7px 11px;background:var(--input-bg);border-left:3px solid var(--text-muted);border-radius:0 6px 6px 0;font-size:11.5px;color:var(--text-secondary);line-height:1.6;}
  .pf-claim{margin:8px 0;padding:9px 12px;border-left:3px solid var(--accent);background:var(--input-bg);border-radius:0 6px 6px 0;font-size:12.5px;line-height:1.7;}
  .pf-claim-num{display:inline-block;font-weight:700;color:var(--accent);margin-right:8px;min-width:56px;}
  .pf-claim-text{color:var(--text-primary);}
  .pf-verdict-card{display:flex;align-items:center;gap:12px;padding:14px 18px;margin:14px 0;border-radius:8px 8px 0 0;}
  .pf-verdict-card-icon{font-size:24px;line-height:1;flex-shrink:0;}
  .pf-verdict-card-label{font-size:12px;color:var(--text-muted);font-weight:600;letter-spacing:.5px;text-transform:uppercase;margin-bottom:2px;}
  .pf-verdict-card-value{font-size:20px;font-weight:800;line-height:1.2;}
  .pf-code{background:rgba(0,0,0,.06);padding:1px 6px;border-radius:4px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em;color:var(--text-primary);}
  .pf-formatted strong{color:var(--text-primary);font-weight:700;}
  @media print{
    body{margin:0;padding:20px;max-width:none;}
    .pf-section,.pf-subsection,.pf-subblock,.pf-claim,.pf-verdict-card{page-break-inside:avoid;}
  }`;

export function buildReportHtml(
  text: string,
  titleLabel: string,
  dateStr: string,
): string {
  const title = escapeHtml(titleLabel);
  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>${title} - ${dateStr}</title>
<style>${EXPORT_CSS}
</style>
</head>
<body>
  <div class="report-header">
    <div class="report-system">${EXPORT_SYSTEM_LABEL}</div>
    <h1 class="report-title">${title}</h1>
    <div class="report-meta">${EXPORT_DATE_LABEL}: ${dateStr}</div>
  </div>
  <div class="report-content">
    ${blocksToHtml(parseReport(text))}
  </div>
  <div class="report-footer">${EXPORT_FOOTER}</div>
</body>
</html>`;
}
