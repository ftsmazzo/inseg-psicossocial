export const JOB_STATUS = {
  draft: { label: "Rascunho", badge: "secondary" },
  processing: { label: "Processando", badge: "warning" },
  review: { label: "Revisão", badge: "info" },
  ready: { label: "Pronto", badge: "success" },
  failed: { label: "Falhou", badge: "danger" },
};

export const LINE_STATUS = {
  discarded: { label: "Descartada", badge: "danger" },
  accepted: { label: "Aceita", badge: "success" },
  Preliminar: { label: "Preliminar", badge: "warning" },
  Proposta: { label: "Proposta", badge: "info" },
  Definitivo: { label: "Definitivo", badge: "success" },
};

export function jobStatusMeta(status) {
  return JOB_STATUS[status] || { label: status, badge: "secondary" };
}

export function lineStatusMeta(line) {
  if (line.discarded) return LINE_STATUS.discarded;
  if (line.accepted) return LINE_STATUS.accepted;
  return LINE_STATUS[line.status] || { label: line.status, badge: "secondary" };
}
