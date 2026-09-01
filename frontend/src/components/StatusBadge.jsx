export default function StatusBadge({ label, badge = "secondary", className = "" }) {
  return (
    <span className={`badge badge-${badge} ${className}`.trim()}>
      {label}
    </span>
  );
}
