/**
 * Centralized educational content for the analysis page.
 *
 * Two exports:
 *  - SECTION_EXPLANATIONS : per-section "Learn more" content shown inline
 *    when the user clicks "Learn more" on a section header. Each entry has
 *    a short title and one or more paragraphs in plain English.
 *
 *  - GLOSSARY : every jargon term used anywhere on the page, with a short
 *    definition + a textbook citation. Shown in the Glossary drawer
 *    accessible from the header.
 *
 * Editing rule: prefer short, concrete, beginner-friendly language over
 * comprehensive definitions. Anyone with a high-school maths background
 * should understand on first read.
 */

// ── Section explanations ─────────────────────────────────────────────────

export const SECTION_EXPLANATIONS = {
  hero: {
    title: 'How to read this analysis',
    body: [
      'The big number is the company\'s current market price. The price gauge below it shows three intrinsic-value estimates our model produced: a Conservative case, a Base case, and an Optimistic case. The market price marker is the black tag.',
      'If all three estimates are below the market price, the model value is below price. If all three are above, the model value is above price. If they straddle the price, small assumption changes can flip the conclusion.',
      'The five colored dots below the gauge are our Confidence Scorecard. Each measures one quality of the analysis (the value gap, the implied growth, the company\'s track record, its balance sheet, and whether DCF even fits this company). 🟢 means safe; 🟡 means caveats; 🔴 means warning.',
    ],
  },

  marketsBet: {
    title: 'What is "the market\'s bet"?',
    body: [
      'Most stock-valuation tools ask: "what is this company worth?" That requires guessing the future, which nobody can do reliably.',
      'OpenQuant asks the reverse question: "what does today\'s price imply about the future?" We hold all other assumptions fixed and SOLVE for the growth rate that makes the model\'s intrinsic value equal to today\'s market price. The result is the growth rate already baked in.',
      'You then compare that implied growth to what the company has actually delivered in the past. If the gap is small, the price is asking the company to do roughly what it has been doing. If the gap is large, the price is betting on a regime change — for better or worse. That gap is the actual investment judgment you have to make.',
    ],
  },

  scenarios: {
    title: 'Why three scenarios?',
    body: [
      'A single model value hides uncertainty. Three scenarios show you the range produced by the same model when you change just two assumptions: the FCF growth rate and the discount rate (WACC).',
      'Conservative: lower growth, higher WACC — penalises the company. Base: median historical growth, current WACC. Optimistic: higher growth, lower WACC — rewards the company.',
      'If all three scenarios agree on the direction, the model gap is robust. If they straddle the market price, the result is fragile — small changes in your beliefs flip the answer.',
    ],
  },

  sliders: {
    title: 'How to use the sliders',
    body: [
      'Our model has chosen specific values for FCF growth (the median of the company\'s recent history), discount rate (computed via WACC and CAPM), and terminal growth (a long-run GDP-anchored 2.5%). You may disagree with any of them.',
      'Drag the sliders and the intrinsic value recomputes live, here in your browser, using exactly the same math the backend used. This is the answer to "what if I do not accept your assumptions?": you can see precisely.',
      'The hint under each slider shows the model\'s default and a reference anchor (historical median, Buffett-style discount, GDP). Use these to calibrate your override.',
    ],
  },

  whatYouNeedToBelieve: {
    title: 'Why list disagreements?',
    body: [
      'The model says one thing; the market says another. For one of them to be wrong, the other has to be right for a specific reason. This section lists those reasons.',
      'Each card states a single specific belief — about growth, about discount rate, about terminal value, about the appropriateness of DCF itself. To take a position against our model, you need to hold at least one of these beliefs.',
      'The point is not to convince you. It is to make the market-implied belief explicit: for today\'s price to make sense, at least one of these views must be true.',
    ],
  },

  multiples: {
    title: 'Why cross-check with multiples?',
    body: [
      'DCF is one valuation approach. Multiples (P/E, EV/EBITDA, FCF yield) are another. They\'re cruder — they compare ratios across companies instead of forecasting cash flows — but they\'re less sensitive to long-horizon assumptions.',
      'If the DCF output, multiples, and FCF yield all point in the same direction, the conclusion is more robust across lenses. If they disagree, one lens is catching something the others miss — and that is a question worth investigating.',
      'For Tesla today, all three multiples flag it as expensive. The DCF agrees. That convergence is itself a signal.',
    ],
  },

  fcfHistory: {
    title: 'What is Free Cash Flow telling us?',
    body: [
      'Free Cash Flow (FCF) is the actual cash the business generated after paying for everything it needs to keep running — operating expenses, taxes, working capital, and capital investments. Unlike accounting "profit", FCF cannot be manipulated by accounting choices.',
      'The textbook FCF formula (Berk-DeMarzo Ch. 7):',
      'FCF = (EBITDA − D&A) × (1 − Tax rate) + D&A − ΔWorking Capital − Capital Expenditure',
      'In the chart, red bars are years where the company burned cash. Blue bars are years where it generated cash. A stable, rising trend is the ideal pattern for DCF — it means the model has a credible base to project from.',
    ],
  },

  sensitivity: {
    title: 'How to read the heatmap',
    body: [
      'The grid shows what the model says the stock is worth at every combination of FCF growth rate (rows) and discount rate (columns). Each cell is an intrinsic value per share.',
      'Green cells = the model would value the stock ABOVE today\'s market price at that combination. Red cells = below. Amber = within ±5% of price. The amber-bordered cell is the (growth, WACC) combination closest to today\'s market price.',
      'Read this to find your "where does the market price sit?" — what combination of growth and discount rate the market is implicitly assuming. That cell is the market\'s implicit position.',
    ],
  },

  wacc: {
    title: 'How WACC is built',
    body: [
      'WACC stands for Weighted Average Cost of Capital. It\'s the discount rate we apply to the company\'s future cash flows — the minimum return a reasonable investor would demand, given the company\'s mix of debt and equity and the risk involved.',
      'The textbook formula (Berk-DeMarzo Ch. 15):',
      'WACC = (E/V) × cost of equity + (D/V) × cost of debt × (1 − tax rate)',
      'Cost of equity comes from CAPM (rf + β × MRP, Ch. 12). Cost of debt comes from the company\'s historical interest expense over its debt base. The tax rate captures the tax shield on interest payments.',
      'Higher WACC → lower intrinsic value. WACC is the single most sensitive input in our DCF. The slider lets you override it.',
    ],
  },

  calibration: {
    title: 'What is "backtest" and why R² = 0.04?',
    body: [
      'A backtest is the financial equivalent of going back in time and asking: "if I had used this model in 2014, would it have been right?"',
      'We took the full pipeline, ran it on 50 S&P 500 stocks "as of" January 2014 (using only data and macro inputs available then), and recorded each valuation conclusion. Then we measured what those stocks actually did from 2014 to 2024.',
      'R² (R-squared) is a statistical measure between 0 and 1 that tells you how much of the variation in real returns the model signal explains. R² = 1 would mean the model explains everything; R² = 0 would mean it explains nothing.',
      'We got R² = 0.04, meaning the model signal explained about 4% of cross-sectional realized returns. That is low. We publish it because it is the truth.',
    ],
  },

  conclusion: {
    title: 'How to use this analysis',
    body: [
      'OpenQuant does not tell you what to do. It surfaces the assumptions that today\'s market price already contains, and tells you honestly how well the model signal worked on historical data.',
      'Use the analysis as a thinking frame: "for this price to make sense, I have to believe X about the company\'s future." If you can name that X clearly, you understand the financial assumption.',
      'And remember the calibration: even when the math is right, the stock-return signal has limited predictive power. Treat the model as one defensible lens, not the answer.',
    ],
  },
}

// ── Glossary ────────────────────────────────────────────────────────────

export const GLOSSARY = [
  { term: 'Berk-DeMarzo', short: 'B&D',
    def: 'The corporate finance textbook this entire project is based on: Jonathan Berk and Peter DeMarzo, Corporate Finance, Pearson 2nd ed. The canonical introductory text for the field.',
  },
  { term: 'Beta (β)', short: 'β',
    def: 'A measure of how much a stock moves relative to the overall market. β=1 moves with the market; β=2 moves twice as much; β=0.5 moves half as much. Used in CAPM. Computed as Cov(stock, market) / Var(market).',
    chapter: 'Ch. 12',
  },
  { term: 'CAPM',
    def: 'Capital Asset Pricing Model. The textbook formula for how risky an asset should be priced: required return = risk-free rate + β × market risk premium.',
    chapter: 'Ch. 12',
  },
  { term: 'DCF',
    def: 'Discounted Cash Flow valuation. The classic method: forecast all future cash flows, discount them back to today using a discount rate (WACC), sum them up. The result is the intrinsic value.',
    chapter: 'Ch. 9',
  },
  { term: 'EBITDA',
    def: 'Earnings Before Interest, Taxes, Depreciation, and Amortization. A measure of operating profitability that removes the effects of capital structure (interest) and accounting choices (D&A).',
    chapter: 'Ch. 7',
  },
  { term: 'EV / EBITDA',
    def: 'A multiple that compares the company\'s enterprise value (market cap + debt − cash) to its EBITDA. A leverage-neutral version of P/E. Useful for comparing companies with very different debt levels.',
  },
  { term: 'Equity bridge',
    def: 'The arithmetic that goes from enterprise value (EV) to equity value: Equity = EV − Net Debt. Then divide by diluted shares to get intrinsic value per share.',
    chapter: 'Ch. 9',
  },
  { term: 'FCF',
    def: 'Free Cash Flow. The actual cash a business generates after paying for everything it needs to keep operating (operating costs + capital expenditure + working capital). Unlike accounting profit, FCF cannot be manipulated by accounting choices.',
    chapter: 'Ch. 7',
  },
  { term: 'FCF yield',
    def: 'FCF per share / market price per share. A "yield" view of the stock — what fraction of your purchase price the company generates in cash each year. Compare to dividend yield or bond yield.',
  },
  { term: 'Growing perpetuity',
    def: 'The textbook formula for the present value of an infinite stream of cash flows growing at rate g, discounted at rate r: PV = C / (r − g). We use it for the DCF terminal value.',
    chapter: 'Ch. 4',
  },
  { term: 'Hamada equation',
    def: 'The textbook formula for adjusting beta when capital structure changes. Lets you "unlever" beta to get the asset-only beta, then "relever" at a different debt/equity ratio. Used in our scenario adjustments.',
    chapter: 'Ch. 15',
  },
  { term: 'Hurdle rate',
    def: 'The minimum return YOU personally require to invest. Our model uses WACC; you may have your own hurdle (e.g. you require 10%/year minimum). Drag the WACC slider to use yours.',
  },
  { term: 'IRR',
    def: 'Internal Rate of Return. The discount rate that would make a project\'s NPV equal to zero — i.e. the project\'s "implicit yield". Used alongside NPV in capital-budgeting decisions.',
    chapter: 'Ch. 8',
  },
  { term: 'Intrinsic value (IV)',
    def: 'What our DCF model outputs for one share, based on projected future cash flows discounted to today. Compare to market price, but do not treat it as a forecast.',
    chapter: 'Ch. 9',
  },
  { term: 'MRP',
    def: 'Market Risk Premium. The extra return investors demand from stocks above the risk-free rate. Historically ~5-6%/year. We use 5.5% by default; Damodaran publishes monthly estimates.',
    chapter: 'Ch. 12',
  },
  { term: 'Margin of safety',
    def: 'Buffett\'s principle that model value should be materially above market price before relying on the gap. It is a tolerance for being wrong.',
  },
  { term: 'NPV',
    def: 'Net Present Value. The sum of all future cash flows discounted to today, minus the initial investment. NPV > 0 → project creates value; NPV < 0 → destroys it.',
    chapter: 'Ch. 8',
  },
  { term: 'P/E',
    def: 'Price-to-Earnings ratio. Share price divided by annual earnings per share. Higher = market expects more future earnings growth. Compare to industry average or S&P 500 average (~22×).',
  },
  { term: 'PVTS',
    def: 'Present Value of Tax Shield. The value created by tax-deductible interest payments on corporate debt. Computed as Σ Debt_{t-1} × interest rate × tax rate / (1+r_D)^t.',
    chapter: 'Ch. 15',
  },
  { term: 'R²',
    def: 'R-squared. Between 0 and 1. Measures how much of the variation in a target variable a model can explain. R² = 1 → perfect; R² = 0 → no better than guessing. Our backtest R² = 0.04.',
  },
  { term: 'Reverse DCF',
    def: 'Instead of asking "what is this stock worth?", solve for the growth rate that would make our DCF\'s intrinsic value equal today\'s market price. The result is the growth rate the market is implicitly assuming.',
  },
  { term: 'Risk-free rate (rf)',
    def: 'The return on a "safe" investment, typically the 10-year US Treasury yield. The baseline against which all riskier returns are compared.',
    chapter: 'Ch. 12',
  },
  { term: 'Sharpe ratio',
    def: 'Excess return per unit of risk: (return − risk-free rate) / volatility. Compares the reward you got for the risk you took. Higher = better risk-adjusted return.',
    chapter: 'Ch. 11',
  },
  { term: 'Terminal value (TV)',
    def: 'The value of all cash flows beyond our explicit 10-year forecast, assumed to grow at a constant rate forever. Computed via growing perpetuity formula. Often 50-70% of total enterprise value.',
    chapter: 'Ch. 9',
  },
  { term: 'WACC',
    def: 'Weighted Average Cost of Capital. The minimum return investors demand given the company\'s risk and capital structure. Used as the DCF discount rate. WACC = (E/V)·cost-of-equity + (D/V)·cost-of-debt·(1−tax).',
    chapter: 'Ch. 15',
  },
]
