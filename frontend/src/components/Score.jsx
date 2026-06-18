export default function Score({ value }) {
  const number = Number(value)
  const safeValue = Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : 0
  return (
    <div className="score">
      <b>{safeValue.toFixed(1)}</b>
      <div><span style={{ width: `${safeValue}%` }} /></div>
    </div>
  )
}
