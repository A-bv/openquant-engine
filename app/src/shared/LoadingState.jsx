export default function LoadingState({ ticker }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 16,
      padding: '80px 0',
      color: '#6B7280',
    }}>
      <div style={{
        width: 40,
        height: 40,
        border: '3px solid #E5E7EB',
        borderTopColor: '#185FA5',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
      <div style={{ fontSize: 15, color: '#111827', fontWeight: 500 }}>
        Analysing {ticker}…
      </div>
      <div style={{ fontSize: 12, color: '#9CA3AF' }}>
        Fetching data from SEC EDGAR
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
