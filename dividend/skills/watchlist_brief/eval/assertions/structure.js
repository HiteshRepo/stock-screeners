/**
 * Structural assertions for the watchlist-brief skill.
 * These are deterministic — no LLM needed.
 */

const REQUIRED_SECTIONS = [
  /### Business snapshot/i,
  /### Dividend quality/i,
  /### Key risks/i,
  /### Portfolio fit/i,
  /### Verdict/i,
];

const VALID_VERDICTS = ['Buy', 'Watch', 'Avoid'];
const VALID_RATINGS  = ['Excellent', 'Good', 'Fair', 'Weak'];

/**
 * All 5 required sections must be present.
 */
function hasAllSections(output) {
  const missing = REQUIRED_SECTIONS.filter(s => !s.test(output));
  if (missing.length > 0) {
    return {
      pass: false,
      score: 0,
      reason: `Missing sections: ${missing.map(r => r.source).join(', ')}`,
    };
  }
  return { pass: true, score: 1, reason: 'All 5 sections present' };
}

/**
 * Verdict must be exactly one of: **Buy**, **Watch**, **Avoid**
 */
function hasValidVerdict(output) {
  const pattern = new RegExp(`\\*\\*(${VALID_VERDICTS.join('|')})\\*\\*`);
  const match = output.match(pattern);
  if (!match) {
    return {
      pass: false,
      score: 0,
      reason: `No valid verdict found. Expected one of: ${VALID_VERDICTS.map(v => `**${v}**`).join(', ')}`,
    };
  }
  return { pass: true, score: 1, reason: `Valid verdict: ${match[1]}` };
}

/**
 * Quality rating must be one of: **Excellent**, **Good**, **Fair**, **Weak**
 * Accepts both standalone (**Good**) and labelled (Quality: **Good**) formats.
 */
function hasValidQualityRating(output) {
  const pattern = new RegExp(`\\*\\*(${VALID_RATINGS.join('|')})\\*\\*`);
  const match = output.match(pattern);
  if (!match) {
    return {
      pass: false,
      score: 0,
      reason: `No valid quality rating found. Expected one of: ${VALID_RATINGS.map(r => `**${r}**`).join(', ')}`,
    };
  }
  return { pass: true, score: 1, reason: `Valid quality rating: ${match[1]}` };
}

/**
 * Key risks section must contain at least 3 list items.
 * Accepts both bullet points (-, *, •) and numbered lists (1., 2., 3.).
 */
function hasKeyRiskBullets(output) {
  const sectionMatch = output.match(/### Key risks([\s\S]*?)(?=###|$)/i);
  if (!sectionMatch) {
    return { pass: false, score: 0, reason: 'Key risks section not found or malformed' };
  }
  const items = (sectionMatch[1].match(/^(\s*[-*•]|\s*\d+\.)\s+\S/gm) || []).length;
  if (items < 3) {
    return {
      pass: false,
      score: 0,
      reason: `Key risks has ${items} item(s); expected at least 3`,
    };
  }
  return { pass: true, score: 1, reason: `Key risks has ${items} item(s)` };
}

module.exports = { hasAllSections, hasValidVerdict, hasValidQualityRating, hasKeyRiskBullets };
