import { useEffect, useMemo, useRef, useState } from "react";

import { Link, useParams } from "react-router-dom";

import { api, downloadJob } from "../api";

import ProgressPanel from "../components/ProgressPanel";

import StatusBadge from "../components/StatusBadge";

import { jobStatusMeta, lineStatusMeta } from "../utils/status";



export default function JobWorkspace() {

  const { id } = useParams();

  const [job, setJob] = useState(null);

  const [selectedId, setSelectedId] = useState(null);

  const [campanhaFile, setCampanhaFile] = useState(null);

  const [pgrFile, setPgrFile] = useState(null);

  const [msg, setMsg] = useState("");

  const [err, setErr] = useState("");

  const [busy, setBusy] = useState(false);

  const [chatInput, setChatInput] = useState("");

  const [chatHistory, setChatHistory] = useState([]);

  const [chatBusy, setChatBusy] = useState(false);

  const [progress, setProgress] = useState(null);

  const [notesOpen, setNotesOpen] = useState(false);

  const pollRef = useRef(null);



  const selected = useMemo(

    () => job?.lines?.find((l) => l.id === selectedId) || job?.lines?.[0],

    [job, selectedId]

  );



  async function load() {

    const data = await api(`/api/jobs/${id}`);

    setJob(data);

    if (data.progress) setProgress(data.progress);

    if (!selectedId && data.lines?.[0]) setSelectedId(data.lines[0].id);

    return data;

  }



  function stopPoll() {

    if (pollRef.current) {

      clearInterval(pollRef.current);

      pollRef.current = null;

    }

  }



  function startPoll() {

    stopPoll();

    pollRef.current = setInterval(async () => {

      try {

        const p = await api(`/api/jobs/${id}/progress`);

        setProgress(p);

        if (p.status && p.status !== "processing") {

          stopPoll();

          setBusy(false);

          await load();

          if (p.status === "review" || p.status === "ready") {

            setMsg("Processamento concluído. Revise as linhas.");

          } else if (p.status === "failed") {

            setErr(p.error_message || "Processamento falhou");

          }

        }

      } catch {

        /* ignore */

      }

    }, 1200);

  }



  useEffect(() => {

    load()

      .then((data) => {

        if (data?.status === "processing") {

          setBusy(true);

          startPoll();

        }

      })

      .catch((e) => setErr(e.message));

    return () => stopPoll();

  }, [id]);



  async function startProcess() {

    setBusy(true);

    setErr("");

    setMsg("");

    setProgress({ done: 0, total: 1, pct: 0, message: "Na fila…", phase: "parse" });

    await api(`/api/jobs/${id}/process`, { method: "POST" });

    startPoll();

  }



  async function uploadAndProcess() {

    setBusy(true);

    setErr("");

    setMsg("");

    try {

      const fd = new FormData();

      if (campanhaFile) fd.append("campanha", campanhaFile);

      if (pgrFile) fd.append("pgr", pgrFile);

      await api(`/api/jobs/${id}/upload`, { method: "POST", body: fd });

      await startProcess();

    } catch (e) {

      setErr(e.message);

      setBusy(false);

      stopPoll();

    }

  }



  async function reprocess() {

    try {

      await startProcess();

    } catch (e) {

      setErr(e.message);

      setBusy(false);

      stopPoll();

    }

  }



  async function patchLine(patch) {

    if (!selected) return;

    setBusy(true);

    setErr("");

    try {

      const updated = await api(`/api/jobs/${id}/lines/${selected.id}`, {

        method: "PATCH",

        json: patch,

      });

      setJob((prev) => ({

        ...prev,

        lines: prev.lines.map((l) => (l.id === updated.id ? updated : l)),

      }));

    } catch (e) {

      setErr(e.message);

    } finally {

      setBusy(false);

    }

  }



  async function acceptAll() {

    setBusy(true);

    try {

      await api(`/api/jobs/${id}/accept-all`, { method: "POST" });

      await load();

      setMsg("Linhas aceitas (memória Inseg atualizada).");

    } catch (e) {

      setErr(e.message);

    } finally {

      setBusy(false);

    }

  }



  async function generate() {

    setBusy(true);

    setErr("");

    try {

      await api(`/api/jobs/${id}/generate`, { method: "POST" });

      await load();

      setMsg("PGR gerado. Faça o download.");

    } catch (e) {

      setErr(e.message);

    } finally {

      setBusy(false);

    }

  }



  async function sendChat(e) {

    e?.preventDefault?.();

    const text = chatInput.trim();

    if (!text || chatBusy) return;

    setChatBusy(true);

    setErr("");

    const historyPayload = chatHistory.map((m) => ({

      role: m.role,

      content: m.content,

    }));

    setChatHistory((h) => [...h, { role: "user", content: text }]);

    setChatInput("");

    try {

      const res = await api(`/api/jobs/${id}/chat`, {

        method: "POST",

        json: {
          message: text,
          history: historyPayload,
          ghe_numero: selected?.ghe_numero || null,
        },

      });

      setChatHistory((h) => [

        ...h,

        {

          role: "assistant",

          content: res.reply,

          meta: res.lines_applied?.length

            ? `Linhas atualizadas: ${res.lines_applied.join(", ")}`

            : null,

        },

      ]);

      if (res.lines_applied?.length) await load();

    } catch (ex) {

      setErr(ex.message);

      setChatHistory((h) => [

        ...h,

        { role: "assistant", content: `Erro: ${ex.message}` },

      ]);

    } finally {

      setChatBusy(false);

    }

  }



  function download() {
    downloadJob(id, `PGR-${id}-psicossocial.docx`).catch((e) => setErr(e.message));
  }



  if (!job) {

    return (

      <section className="content">

        <div className="container-fluid py-5 text-center text-muted">

          <i className="fas fa-spinner fa-spin mr-1" />

          {err || "Carregando job…"}

        </div>

      </section>

    );

  }



  const canUpload = job.status === "draft" || job.status === "failed";

  const incompleteReview =
    job.status === "review" &&
    job.progress?.total > 0 &&
    job.lines_count > 0 &&
    job.lines_count < job.progress.total;

  const canReprocess =
    job.status === "review" ||
    job.status === "ready" ||
    job.status === "failed" ||
    incompleteReview ||
    (job.status === "processing" && job.processing_stale);

  const showProgress = job.status === "processing" || (busy && progress);

  const jobSt = jobStatusMeta(job.status);



  return (

    <>

      <section className="content-header">

        <div className="container-fluid">

          <div className="row mb-2 align-items-center">

            <div className="col-sm-6">

              <h1 className="m-0">{job.title}</h1>

              <p className="text-muted mb-0 mt-1">

                {job.empresa || "Empresa pendente"}

                {job.cnpj ? ` · CNPJ ${job.cnpj}` : ""}

              </p>

            </div>

            <div className="col-sm-6">

              <ol className="breadcrumb float-sm-right">

                <li className="breadcrumb-item">

                  <Link to="/">Jobs</Link>

                </li>

                <li className="breadcrumb-item active">{job.title}</li>

              </ol>

            </div>

          </div>



          <div className="d-flex flex-wrap align-items-center mb-2">

            <StatusBadge label={jobSt.label} badge={jobSt.badge} className="mr-2 mb-2" />

            {job.lines_count > 0 && (

              <span className="text-muted small mb-2 mr-3">

                {job.accepted_count}/{job.lines_count} linhas aceitas

              </span>

            )}

            <div className="ml-auto d-flex flex-wrap">

              {canReprocess && (

                <button

                  className="btn btn-outline-secondary btn-sm mr-1 mb-2"

                  disabled={busy}

                  onClick={reprocess}

                >

                  <i className="fas fa-redo mr-1" />

                  {job.status === "processing" && job.processing_stale
                    ? "Continuar processamento"
                    : incompleteReview
                      ? "Continuar processamento"
                      : "Reprocessar"}

                </button>

              )}

              <button

                className="btn btn-outline-success btn-sm mr-1 mb-2"

                disabled={busy || !job.lines?.length}

                onClick={acceptAll}

              >

                <i className="fas fa-check-double mr-1" />

                Aceitar todas

              </button>

              <button

                className="btn btn-primary btn-sm mr-1 mb-2"

                disabled={busy || !job.lines?.length}

                onClick={generate}

              >

                <i className="fas fa-file-word mr-1" />

                Gerar PGR

              </button>

              {job.status === "ready" && (

                <button className="btn btn-success btn-sm mb-2" onClick={download}>

                  <i className="fas fa-download mr-1" />

                  Baixar DOCX

                </button>

              )}

            </div>

          </div>

        </div>

      </section>



      <section className="content">

        <div className="container-fluid">

          {err && (

            <div className="alert alert-danger alert-dismissible">

              <button type="button" className="close" onClick={() => setErr("")}>

                <span>&times;</span>

              </button>

              {err}

            </div>

          )}

          {msg && (

            <div className="alert alert-success alert-dismissible">

              <button type="button" className="close" onClick={() => setMsg("")}>

                <span>&times;</span>

              </button>

              {msg}

            </div>

          )}



          {showProgress && <ProgressPanel progress={progress} status={job.status} />}



          {canUpload && (

            <div className="card card-primary card-outline mb-3">

              <div className="card-header">

                <h3 className="card-title">

                  <i className="fas fa-cloud-upload-alt mr-1" />

                  Upload e processamento

                </h3>

              </div>

              <div className="card-body">

                <div className="row">

                  <div className="col-md-6 mb-3">

                    <FileDrop

                      label="Campanha CST (PDF)"

                      icon="fa-file-pdf"

                      accept=".pdf"

                      file={campanhaFile}

                      fallback={job.campanha_path ? "Arquivo já enviado" : null}

                      onPick={setCampanhaFile}

                    />

                  </div>

                  <div className="col-md-6 mb-3">

                    <FileDrop

                      label="PGR Inseg (DOCX)"

                      icon="fa-file-word"

                      accept=".docx"

                      file={pgrFile}

                      fallback={job.pgr_path ? "Arquivo já enviado" : null}

                      onPick={setPgrFile}

                    />

                  </div>

                </div>

                <button

                  className="btn btn-primary"

                  disabled={

                    busy ||

                    (!campanhaFile && !job.campanha_path) ||

                    (!pgrFile && !job.pgr_path)

                  }

                  onClick={uploadAndProcess}

                >

                  {busy ? (

                    <>

                      <i className="fas fa-spinner fa-spin mr-1" />

                      Processando…

                    </>

                  ) : (

                    <>

                      <i className="fas fa-play mr-1" />

                      Processar

                    </>

                  )}

                </button>

                {job.error_message && (

                  <p className="text-danger mt-2 mb-0">{job.error_message}</p>

                )}

              </div>

            </div>

          )}



          {!!job.lines?.length && (

            <div className="row">

              <div className="col-xl-3 col-lg-4 mb-3">

                <div className="card card-outline card-secondary h-100">

                  <div className="card-header">

                    <h3 className="card-title">GHEs ({job.lines.length})</h3>

                  </div>

                  <div className="card-body p-0 inseg-ghe-list">

                    <div className="list-group list-group-flush">

                      {job.lines.map((l) => {

                        const st = lineStatusMeta(l);

                        return (

                          <button

                            key={l.id}

                            type="button"

                            className={`list-group-item list-group-item-action inseg-ghe-item text-left ${

                              selected?.id === l.id ? "active" : ""

                            }`}

                            onClick={() => setSelectedId(l.id)}

                          >

                            <div className="d-flex justify-content-between align-items-start">

                              <strong className="small">

                                GHE {l.ghe_numero}

                              </strong>

                              <StatusBadge label={st.label} badge={st.badge} />

                            </div>

                            <div className="small text-muted text-truncate">

                              {l.hazard_id}

                            </div>

                            <div className="small text-truncate">{l.agente}</div>

                          </button>

                        );

                      })}

                    </div>

                  </div>

                </div>

              </div>



              <div className="col-xl-6 col-lg-8 mb-3">

                {selected && (

                  <div className="card card-outline card-primary h-100">

                    <div className="card-header">

                      <h3 className="card-title">

                        GHE {selected.ghe_numero} — {selected.ghe_nome}

                      </h3>

                    </div>

                    <div className="card-body inseg-field-scroll">

                      <p className="text-muted small">

                        n={selected.n_respondentes} · match{" "}

                        {selected.match_score.toFixed(2)} · {selected.matched_from}

                      </p>



                      <Field

                        label="Agente / Perigo"

                        value={selected.agente}

                        onChange={(v) => patchLine({ agente: v })}

                      />

                      <Field

                        label="Exposição"

                        value={selected.exposicao}

                        onChange={(v) => patchLine({ exposicao: v })}

                        area

                      />

                      <Field

                        label="Causa / Fonte"

                        value={selected.causa_fonte}

                        onChange={(v) => patchLine({ causa_fonte: v })}

                        area

                      />

                      <Field

                        label="Trajetória"

                        value={selected.trajetoria}

                        onChange={(v) => patchLine({ trajetoria: v })}

                        area

                      />

                      <Field

                        label="Danos"

                        value={selected.danos}

                        onChange={(v) => patchLine({ danos: v })}

                        area

                      />



                      <div className="form-row">

                        <div className="form-group col-md-4">

                          <label>Grau de Exposição</label>

                          <select

                            className="form-control form-control-sm"

                            value={selected.grau_exposicao}

                            onChange={(e) =>

                              patchLine({ grau_exposicao: Number(e.target.value) })

                            }

                          >

                            {[1, 2, 3, 4, 5].map((n) => (

                              <option key={n} value={n}>

                                {n}

                              </option>

                            ))}

                          </select>

                        </div>

                        <div className="form-group col-md-4">

                          <label>Grau do Efeito</label>

                          <select

                            className="form-control form-control-sm"

                            value={selected.grau_efeito}

                            onChange={(e) =>

                              patchLine({ grau_efeito: Number(e.target.value) })

                            }

                          >

                            {[1, 2, 3, 4, 5].map((n) => (

                              <option key={n} value={n}>

                                {n}

                              </option>

                            ))}

                          </select>

                        </div>

                        <div className="form-group col-md-4">

                          <label>Potencial</label>

                          <input

                            className="form-control form-control-sm"

                            value={selected.potencial}

                            readOnly

                          />

                        </div>

                      </div>



                      <div className="form-row">

                        <div className="form-group col-md-4">

                          <label>Prioridade de ação</label>

                          <input

                            className="form-control form-control-sm"

                            value={

                              selected.prioridade_acao

                                ? `P${selected.prioridade_acao}`

                                : "—"

                            }

                            readOnly

                            title="Prioridade de intervenção (≠ potencial da matriz)"

                          />

                        </div>

                        {selected.motor_rationale && (

                          <div className="form-group col-md-8">

                            <label>Análise do motor</label>

                            <p className="small text-muted mb-0 border rounded p-2 bg-light">

                              {selected.motor_rationale}

                            </p>

                          </div>

                        )}

                      </div>



                      <Field

                        label="Controles"

                        value={selected.controles}

                        onChange={(v) => patchLine({ controles: v })}

                        area

                      />



                      <div className="form-group">

                        <label>Evidências</label>

                        <ul className="small text-muted mb-0 pl-3">

                          {(selected.evidencias_json || []).map((e, i) => (

                            <li key={i}>{e}</li>

                          ))}

                        </ul>

                      </div>



                      <div className="d-flex flex-wrap">

                        <button

                          className="btn btn-success btn-sm mr-2 mb-2"

                          disabled={busy}

                          onClick={() => patchLine({ accepted: true, discarded: false })}

                        >

                          <i className="fas fa-check mr-1" />

                          Aceitar

                        </button>

                        <button

                          className="btn btn-outline-danger btn-sm mb-2"

                          disabled={busy}

                          onClick={() => patchLine({ discarded: true, accepted: false })}

                        >

                          <i className="fas fa-times mr-1" />

                          Descartar

                        </button>

                      </div>

                    </div>

                  </div>

                )}

              </div>



              <div className="col-xl-3 mb-3">

                <div className="card card-outline card-info h-100">

                  <div className="card-header">

                    <h3 className="card-title">

                      <i className="fas fa-robot mr-1" />

                      Agente do job

                    </h3>

                  </div>

                  <div className="card-body d-flex flex-column">

                    <p className="text-muted small">

                      Converse à vontade (objetivar, filtrar, explicar). Para gravar na linha, diga <strong>aplica</strong> ou <strong>salva</strong>.

                    </p>

                    <div className="inseg-chat-log flex-grow-1 mb-2">

                      {chatHistory.length === 0 && (

                        <p className="text-muted small mb-0">Nenhuma mensagem ainda.</p>

                      )}

                      {chatHistory.map((m, i) => (

                        <div key={i} className={`inseg-chat-bubble ${m.role}`}>

                          <strong className="small d-block mb-1">

                            {m.role === "user" ? "Você" : "Agente"}

                          </strong>

                          <div className="small">{m.content}</div>

                          {m.meta && (

                            <small className="text-muted d-block mt-1">{m.meta}</small>

                          )}

                        </div>

                      ))}

                    </div>

                    <form onSubmit={sendChat}>

                      <div className="input-group input-group-sm">

                        <input

                          className="form-control"

                          value={chatInput}

                          disabled={chatBusy}

                          placeholder={

                            selected

                              ? `GHE ${selected.ghe_numero}…`

                              : "Escreva sua pergunta…"

                          }

                          onChange={(e) => setChatInput(e.target.value)}

                        />

                        <div className="input-group-append">

                          <button

                            className="btn btn-primary"

                            disabled={chatBusy || !chatInput.trim()}

                            type="submit"

                          >

                            {chatBusy ? "…" : "Enviar"}

                          </button>

                        </div>

                      </div>

                    </form>

                  </div>

                </div>

              </div>

            </div>

          )}



          {!!job.notes_json?.length && (
            <div className={`card card-outline card-secondary ${notesOpen ? "" : "collapsed-card"}`}>
              <div className="card-header">
                <h3 className="card-title">Notas do motor</h3>
                <div className="card-tools">
                  <button
                    type="button"
                    className="btn btn-tool"
                    onClick={() => setNotesOpen((v) => !v)}
                    aria-expanded={notesOpen}
                  >
                    <i className={`fas ${notesOpen ? "fa-minus" : "fa-plus"}`} />
                  </button>
                </div>
              </div>
              {notesOpen && (
                <div className="card-body">
                  <ul className="small text-muted mb-0 pl-3">
                    {job.notes_json.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

        </div>

      </section>

    </>

  );

}



function FileDrop({ label, icon, accept, file, fallback, onPick }) {

  const inputId = `file-${label.replace(/\W+/g, "-")}`;

  return (

    <label htmlFor={inputId} className="inseg-drop-zone mb-0 w-100">

      <input

        id={inputId}

        type="file"

        accept={accept}

        onChange={(e) => onPick(e.target.files?.[0] || null)}

      />

      <i className={`fas ${icon} fa-2x text-muted mb-2`} />

      <strong className="d-block">{label}</strong>

      <span className="small text-muted">

        {file?.name || fallback || "Clique para selecionar"}

      </span>

    </label>

  );

}



function Field({ label, value, onChange, area }) {

  const [local, setLocal] = useState(value);

  useEffect(() => setLocal(value), [value]);

  const Comp = area ? "textarea" : "input";

  return (

    <div className="form-group">

      <label className="small font-weight-bold">{label}</label>

      <Comp

        className={`form-control form-control-sm ${area ? "" : ""}`}

        rows={area ? 3 : undefined}

        value={local}

        onChange={(e) => setLocal(e.target.value)}

        onBlur={() => {

          if (local !== value) onChange(local);

        }}

      />

    </div>

  );

}

