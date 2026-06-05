export default function GaugeChart({ score, color, size = 110 }) {
  const radius = (size - 12) / 2
  const circumference = 2 * Math.PI * radius
  const progress = (score / 100) * circumference
  const remaining = circumference - progress

  return (
    <div className="gauge-circle" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e8ede5"
          strokeWidth="10"
        />
        {/* Progress arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${progress} ${remaining}`}
          style={{ transition: 'stroke-dasharray 0.8s ease' }}
        />
      </svg>
      <div className="gauge-center-text">
        <div className="gauge-score-value">{score}</div>
        <div className="gauge-score-max">/100</div>
      </div>
    </div>
  )
}
