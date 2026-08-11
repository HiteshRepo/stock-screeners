/**
 * Structural assertions for the portfolio-narrative skill.
 * portfolio_narrative produces free-form paragraphs — no fixed section headers.
 */

/**
 * Output must have at least 3 paragraphs (separated by blank lines).
 * The prompt asks for a 3–4 paragraph briefing.
 */
function hasParagraphs(output) {
  const paragraphs = output
    .split(/\n\s*\n/)
    .map(p => p.trim())
    .filter(p => p.length > 40);  // ignore stray short lines
  if (paragraphs.length < 3) {
    return {
      pass: false,
      score: 0,
      reason: `Expected at least 3 paragraphs, found ${paragraphs.length}`,
    };
  }
  return { pass: true, score: 1, reason: `Found ${paragraphs.length} paragraphs` };
}

/**
 * The prompt explicitly says "No headers needed" — output should not use markdown
 * headers (## or ###) as section dividers.
 */
function noSectionHeaders(output) {
  const headerPattern = /^#{2,}\s+\w/m;
  if (headerPattern.test(output)) {
    return {
      pass: false,
      score: 0,
      reason: 'Output uses markdown section headers (## or ###), which the prompt disallows',
    };
  }
  return { pass: true, score: 1, reason: 'No section headers — correct prose format' };
}

module.exports = { hasParagraphs, noSectionHeaders };
