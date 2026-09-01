export default function ProgressPanel({ progress, status }) {
  if (!progress && status !== "processing") return null;

  const done = progress?.done ?? 0;
  const total = Math.max(progress?.total ?? 1, 1);
  const pct = Math.min(
    100,
    Math.max(0, Number(progress?.pct ?? (100 * done) / total))
  );
  const msg = progress?.message || "Processando…";
  const ghe = progress?.ghe || "";
  const phase = progress?.phase || "filling";

  return (
    <div className="card card-outline card-warning mb-3">
      <div className="card-header">
        <h3 className="card-title">
          <i className="fas fa-cog fa-spin mr-2" />
          Progresso do motor
        </h3>
        <div className="card-tools">
          <span className="badge badge-warning">
            {done}/{total} · {pct.toFixed(0)}%
          </span>
        </div>
      </div>
      <div className="card-body">
        <div
          className="progress progress-sm mb-2"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
        >
          <div
            className="progress-bar bg-warning progress-bar-striped progress-bar-animated"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="mb-1">{msg}</p>
        {phase && (
          <small className="text-muted text-uppercase d-block mb-1">
            Fase: {phase}
          </small>
        )}
        {ghe ? (
          <small className="text-muted">
            <i className="fas fa-layer-group mr-1" />
            GHE {ghe}
          </small>
        ) : null}
      </div>
    </div>
  );
}
