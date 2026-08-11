/**
 * Content quality assertions for the watchlist-brief skill.
 * These check that the model actually used the market data provided.
 */

/**
 * The output must cite at least one numeric value with a financial unit (%, ₹, x).
 * Ensures the model isn't ignoring the market_data JSON.
 */
function citesNumbers(output) {
  // Match patterns like: 5.8%, ₹285, 44%, 32x, 2.1%
  const pattern = /\d+\.?\d*\s*(%|₹|x\b)/;
  if (!pattern.test(output)) {
    return {
      pass: false,
      score: 0,
      reason: 'Output does not cite any numeric values with financial units (%, ₹, x)',
    };
  }
  return { pass: true, score: 1, reason: 'Output cites numeric values from market data' };
}

module.exports = { citesNumbers };
