import { HTML_PREVIEW_CSP } from './html-preview-policy';

/** A trusted outer document owns frame-src, including the guest's self-navigation. */
export function htmlPreviewDocument(
  html: string,
  channel: string,
  title: string,
): string {
  const serialize = (value: string) =>
    JSON.stringify(value).replaceAll('<', '\\u003c');
  const diagnostic = `<script>(()=>{const report=()=>parent.postMessage({channel:${serialize(channel)},type:'preview-error'},'*');addEventListener('error',report,true);addEventListener('unhandledrejection',report);addEventListener('securitypolicyviolation',report);})();</script>`;
  const guest = `<meta http-equiv="Content-Security-Policy" content="${HTML_PREVIEW_CSP}">${diagnostic}${html}`;
  return `<!doctype html><meta http-equiv="Content-Security-Policy" content="${HTML_PREVIEW_CSP}">
<style>html,body,iframe{width:100%;height:100%;margin:0;border:0;display:block;overflow:hidden}</style>
<script>(()=>{const channel=${serialize(channel)};const report=()=>parent.postMessage({channel:${serialize(channel)},type:'preview-error'},'*');
addEventListener('securitypolicyviolation',report);
const guest=document.createElement('iframe');guest.title=${serialize(title)};guest.setAttribute('sandbox','allow-scripts');guest.referrerPolicy='no-referrer';
addEventListener('message',event=>{if(event.source===guest.contentWindow&&event.data?.channel===channel&&event.data?.type==='preview-error')report()});
guest.srcdoc=${serialize(guest)};addEventListener('DOMContentLoaded',()=>document.body.appendChild(guest));})();</script><body></body>`;
}
