import {
  BarChart, Bar, Cell, ReferenceLine,
  XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList,
} from 'recharts'

const pct = v => v == null ? '—' : `${(v * 100).toFixed(1)}%`

const CLAMP = 150 // percent — cap display range so one extreme bar can't blow the axis

function CustomTick({ x, y, payload }) {
  if (!payload?.value) return null
  const parts = payload.value.split('|')
  return (
    <g transform={`translate(${x},${y})`}>
      {parts.map((p, i) => (
        <text
          key={i}
          x={0}
          y={0}
          dy={14 + i * 13}
          textAnchor="middle"
          fill="#6B7280"
          fontSize={10}
        >
          {p}
        </text>
      ))}
    </g>
  )
}

function BarLabel({ x, y, width, height, value, actualValue, clamped }) {
  if (value == null || isNaN(value)) return null
  const positive = value >= 0
  const label = `${Number(actualValue ?? value).toFixed(1)}%${clamped ? '*' : ''}`
  // For negative bars: y = bar tip (SVG bottom), height = bar height.
  // Anchoring near y - height + 18 (zero-line end of bar) prevents the
  // clamped extreme label (e.g. -2368%*) from sitting at the SVG edge.
  const textY = positive
    ? y - 6
    : (height != null && height > 20 ? y - height + 18 : y - 6)
  return (
    <text
      x={x + width / 2}
      y={textY}
      fill="#6B7280"
      textAnchor="middle"
      fontSize={11}
      fontWeight={500}
    >
      {label}
    </text>
  )
}

function RefLabel({ viewBox, label }) {
  if (!viewBox) return null
  const { x, width, y } = viewBox
  return (
    <text
      x={x + width - 4}
      y={y - 4}
      textAnchor="end"
      fill="#185FA5"
      fontSize={10}
    >
      {label}
    </text>
  )
}

export default function ReverseChart({ revDcf }) {
  const {
    implied_growth, historical_median, historical_mean,
    revenue_cagr, gdp_growth,
  } = revDcf

  const rawData = [
    { name: 'Implied|Growth',  value: (implied_growth   ?? 0) * 100, raw: implied_growth,       implied: true },
    { name: 'Hist.|Median',    value: (historical_median ?? 0) * 100, raw: historical_median },
    { name: 'Hist.|Mean',      value: (historical_mean   ?? 0) * 100, raw: historical_mean  },
    { name: 'Rev.|CAGR',       value: (revenue_cagr      ?? 0) * 100, raw: revenue_cagr     },
    { name: 'GDP|Growth',      value: (gdp_growth        ?? 0.03) * 100, raw: gdp_growth ?? 0.03 },
  ]

  const data = rawData.map(d => ({
    ...d,
    displayValue: Math.max(-CLAMP, Math.min(CLAMP, d.value)),
    clamped: Math.abs(d.value) > CLAMP,
  }))

  const impliedColor = (implied_growth ?? 0) >= (historical_median ?? 0) ? '#3B6D11' : '#A32D2D'
  const refY = (historical_median ?? 0) * 100
  const refLabel = `Historical median ${pct(historical_median)}`

  // Domain based only on non-extreme values so one outlier can't collapse everything
  const visible = data.filter(d => !d.clamped)
  const yMax = Math.ceil(Math.max(...visible.map(d => d.value), refY, 10) * 1.3)
  const yMin = Math.floor(Math.min(...visible.map(d => d.value), 0) * 1.3)

  const hasClamped = data.some(d => d.clamped)

  return (
    <div style={{ width: '100%', height: 280 }}>
      {hasClamped && (
        <div style={{ fontSize: 10, color: '#9CA3AF', marginBottom: 2, textAlign: 'right' }}>
          * bar truncated for scale; label shows actual value
        </div>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 24, right: 24, left: 0, bottom: 50 }} barSize={44}>
          <XAxis
            dataKey="name"
            tick={CustomTick}
            interval={0}
            axisLine={false}
            tickLine={false}
            height={50}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#9CA3AF' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={v => `${v}%`}
            width={42}
            domain={[yMin, yMax]}
          />
          <Tooltip
            formatter={(v, _n, item) => [pct(item?.payload?.raw ?? v / 100), '']}
            labelFormatter={l => l.replace(/\|/g, ' ')}
            contentStyle={{ border: '0.5px solid #E5E7EB', borderRadius: 8, fontSize: 12 }}
          />
          <ReferenceLine
            y={refY}
            stroke="#185FA5"
            strokeDasharray="4 3"
            strokeWidth={1.5}
            label={<RefLabel label={refLabel} />}
          />
          <Bar dataKey="displayValue" radius={[4, 4, 0, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.implied ? impliedColor : '#B4B2A9'} fillOpacity={0.9} />
            ))}
            <LabelList
              dataKey="displayValue"
              content={(props) => {
                const entry = data[props.index]
                return (
                  <BarLabel
                    {...props}
                    actualValue={entry?.value}
                    clamped={entry?.clamped}
                  />
                )
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
