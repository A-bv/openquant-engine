import {
  BarChart, Bar, Cell, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, LabelList,
} from 'recharts'

function BarLabel({ x, y, width, height, value }) {
  if (value == null || isNaN(value)) return null
  const positive = value >= 0
  const b = value / 1e9
  const rounded = Math.abs(b).toFixed(1)
  const sign = b < 0 && parseFloat(rounded) > 0 ? '-' : ''
  // For negative bars Recharts passes y = bar tip (SVG bottom).
  // Anchoring near y - height + 14 (zero-line end of bar) keeps the
  // label well clear of the SVG clip boundary at the chart bottom.
  const textY = positive
    ? y - 5
    : (height != null && height > 16 ? y - height + 14 : y - 5)
  return (
    <text
      x={x + width / 2}
      y={textY}
      textAnchor="middle"
      fill={positive ? '#185FA5' : 'white'}
      fontSize={10}
      fontWeight={600}
    >
      {sign}${rounded}B
    </text>
  )
}

export default function FCFHistoryChart({ history, companyName }) {
  if (!history?.length) return null

  const data = history.map(d => ({ year: String(d.year), fcf: d.fcf }))

  // Compute a simple linear trend from the points with finite FCF only.
  // If <2 finite points survive, skip the trend overlay rather than
  // letting NaN poison the dataset (Recharts silently drops NaN points
  // but the user expects a visible regression line).
  const finitePts = data
    .map((d, i) => ({ x: i, y: Number.isFinite(d.fcf) ? d.fcf / 1e9 : null }))
    .filter(p => p.y != null)
  let slope = 0, intercept = 0, haveTrend = false
  if (finitePts.length >= 2) {
    const xMean = finitePts.reduce((a, p) => a + p.x, 0) / finitePts.length
    const yMean = finitePts.reduce((a, p) => a + p.y, 0) / finitePts.length
    const denom = finitePts.reduce((s, p) => s + (p.x - xMean) ** 2, 0)
    if (denom > 0) {
      slope = finitePts.reduce((s, p) => s + (p.x - xMean) * (p.y - yMean), 0) / denom
      intercept = yMean - slope * xMean
      haveTrend = true
    }
  }

  const dataWithTrend = data.map((d, i) => ({
    ...d,
    trend: haveTrend ? slope * i + intercept : null,
  }))

  const allPositive = data.every(d => d.fcf >= 0)
  const refY = allPositive ? undefined : 0

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827', marginBottom: 8 }}>
        {companyName} — Free Cash Flow History
      </div>
      <div style={{ width: '100%', height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={dataWithTrend} margin={{ top: 24, right: 16, left: 0, bottom: 4 }} barSize={32}>
            <XAxis
              dataKey="year"
              tick={{ fontSize: 11, fill: '#9CA3AF' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: '#9CA3AF' }}
              axisLine={false}
              tickLine={false}
              tickFormatter={v => `$${(v / 1e9).toFixed(0)}B`}
              width={48}
              domain={['auto', 'auto']}
            />
            <Tooltip
              formatter={v => [`$${(v / 1e9).toFixed(1)}B`, 'FCF']}
              contentStyle={{ border: '0.5px solid #E5E7EB', borderRadius: 8, fontSize: 12 }}
            />
            {refY !== undefined && (
              <ReferenceLine y={0} stroke="#E5E7EB" strokeWidth={1} />
            )}
            <Bar dataKey="fcf" radius={[3, 3, 0, 0]}>
              {dataWithTrend.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.fcf >= 0 ? '#185FA5' : '#A32D2D'}
                  fillOpacity={0.85}
                />
              ))}
              <LabelList dataKey="fcf" content={BarLabel} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
