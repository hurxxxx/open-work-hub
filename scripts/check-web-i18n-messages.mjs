#!/usr/bin/env node
import {
  findWebI18nFindings,
  formatWebI18nFindings,
} from './web-i18n-message-checker.mjs';

const FAIL = process.argv.includes('--fail-on-findings');
const findings = findWebI18nFindings();

console.log(formatWebI18nFindings(findings));

if (FAIL && findings.length > 0) {
  process.exitCode = 1;
}
