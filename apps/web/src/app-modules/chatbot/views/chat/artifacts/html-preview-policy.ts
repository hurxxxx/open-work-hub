// Scripts may use embedded bytes, never a network origin. The iframe also
// retains an opaque origin (allow-scripts only) and cannot access app state.
export const HTML_PREVIEW_CSP =
  "default-src 'none'; script-src 'unsafe-inline' data:; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'";
