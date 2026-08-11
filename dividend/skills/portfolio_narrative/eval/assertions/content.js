/**
 * Content quality assertions for the portfolio-narrative skill.
 */

/**
 * Output must cite at least two ₹ values (performance + income both need numbers).
 */
function citesRupeeValues(output) {
  const matches = output.match(/₹[\d,]+/g) || [];
  if (matches.length < 2) {
    return {
      pass: false,
      score: 0,
      reason: `Found only ${matches.length} ₹ value(s); expected at least 2`,
    };
  }
  return { pass: true, score: 1, reason: `Found ${matches.length} ₹ value(s)` };
}

/**
 * Output must mention annual dividend income in ₹ per year.
 * Looks for phrases like "₹X per year", "annual income", "annual dividend", etc.
 */
function mentionsDividendIncome(output) {
  const incomePattern = /(annual|per year|yearly|dividend income)/i;
  if (!incomePattern.test(output)) {
    return {
      pass: false,
      score: 0,
      reason: 'Output does not mention annual dividend income',
    };
  }
  return { pass: true, score: 1, reason: 'Annual dividend income is mentioned' };
}

module.exports = { citesRupeeValues, mentionsDividendIncome };
