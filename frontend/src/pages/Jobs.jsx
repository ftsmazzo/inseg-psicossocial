import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, downloadJob } from "../api";
import StatusBadge from "../components/StatusBadge";
import { jobStatusMeta } from "../utils/status";


export default function Jobs() {

  const [jobs, setJobs] = useState([]);

  const [title, setTitle] = useState("");

  const [error, setError] = useState("");

  const [loading, setLoading] = useState(true);

  const [deletingId, setDeletingId] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);
  const nav = useNavigate();


  async function load() {

    setLoading(true);

    try {

      const list = await api("/api/jobs");

      setJobs(list);

      setError("");

    } catch (err) {

      setError(err.message);

    } finally {

      setLoading(false);

    }

  }



  useEffect(() => {

    load();

  }, []);



  async function createJob(e) {

    e.preventDefault();

    setError("");

    try {

      const job = await api("/api/jobs", {

        method: "POST",

        json: { title: title || `Job ${new Date().toLocaleString("pt-BR")}` },

      });

      setTitle("");

      nav(`/jobs/${job.id}`);

    } catch (err) {

      setError(err.message);

    }

  }



  async function removeJob(job) {

    if (

      !window.confirm(

        `Excluir o job "${job.title}"?\n\nArquivos, linhas e propostas serão apagados. Não dá para desfazer.`

      )

    ) {

      return;

    }

    setError("");

    setDeletingId(job.id);

    try {

      await api(`/api/jobs/${job.id}`, { method: "DELETE" });

      setJobs((prev) => prev.filter((j) => j.id !== job.id));

    } catch (err) {

      setError(err.message);

    } finally {

      setDeletingId(null);

    }

  }



  async function handleDownload(job) {
    setError("");
    setDownloadingId(job.id);
    try {
      await downloadJob(job.id, `PGR-${job.id}-original.docx`);
    } catch (err) {
      setError(err.message);
    } finally {
      setDownloadingId(null);
    }
  }

  const stats = {
    total: jobs.length,

    review: jobs.filter((j) => j.status === "review").length,

    ready: jobs.filter((j) => j.status === "ready").length,

    processing: jobs.filter((j) => j.status === "processing").length,

  };



  return (

    <>

      <section className="content-header">

        <div className="container-fluid">

          <div className="row mb-2">

            <div className="col-sm-6">

              <h1 className="m-0">Jobs</h1>

            </div>

            <div className="col-sm-6">

              <ol className="breadcrumb float-sm-right">

                <li className="breadcrumb-item active">Jobs</li>

              </ol>

            </div>

          </div>

        </div>

      </section>



      <section className="content">

        <div className="container-fluid">

          <div className="row">

            <div className="col-lg-3 col-6">

              <div className="small-box bg-info">

                <div className="inner">

                  <h3>{stats.total}</h3>

                  <p>Total de jobs</p>

                </div>

                <div className="icon">

                  <i className="fas fa-folder-open" />

                </div>

              </div>

            </div>

            <div className="col-lg-3 col-6">

              <div className="small-box bg-warning">

                <div className="inner">

                  <h3>{stats.review + stats.processing}</h3>

                  <p>Em andamento</p>

                </div>

                <div className="icon">

                  <i className="fas fa-tasks" />

                </div>

              </div>

            </div>

            <div className="col-lg-3 col-6">

              <div className="small-box bg-success">

                <div className="inner">

                  <h3>{stats.ready}</h3>

                  <p>Prontos p/ download</p>

                </div>

                <div className="icon">

                  <i className="fas fa-file-download" />

                </div>

              </div>

            </div>

          </div>



          <div className="card card-primary card-outline">

            <div className="card-header">

              <h3 className="card-title">Novo job</h3>

            </div>

            <div className="card-body">

              <form className="form-inline flex-wrap" onSubmit={createJob}>

                <div className="form-group flex-grow-1 mr-2 mb-2" style={{ minWidth: 240 }}>

                  <input

                    className="form-control w-100"

                    placeholder="Nome do job (ex.: Polimetal 2026)"

                    value={title}

                    onChange={(e) => setTitle(e.target.value)}

                  />

                </div>

                <button type="submit" className="btn btn-primary mb-2">

                  <i className="fas fa-plus mr-1" />

                  Criar job

                </button>

              </form>

            </div>

          </div>



          {error && (

            <div className="alert alert-danger" role="alert">

              {error}

            </div>

          )}



          <div className="card">

            <div className="card-header">

              <h3 className="card-title">Seus jobs</h3>

            </div>

            <div className="card-body table-responsive p-0">

              <table className="table table-hover table-striped mb-0">

                <thead>

                  <tr>

                    <th>Job</th>

                    <th>Empresa</th>

                    <th>Status</th>

                    <th>Linhas aceitas</th>

                    <th className="text-right">Ações</th>

                  </tr>

                </thead>

                <tbody>

                  {loading && (

                    <tr>

                      <td colSpan={5} className="text-center text-muted py-4">

                        <i className="fas fa-spinner fa-spin mr-1" />

                        Carregando…

                      </td>

                    </tr>

                  )}

                  {!loading &&

                    jobs.map((j) => {

                      const st = jobStatusMeta(j.status);

                      return (

                        <tr key={j.id}>

                          <td>

                            <strong>{j.title}</strong>

                            {j.progress?.message && j.status === "processing" && (

                              <div className="small text-muted">{j.progress.message}</div>

                            )}

                          </td>

                          <td>{j.empresa || "—"}</td>

                          <td>

                            <StatusBadge label={st.label} badge={st.badge} />

                          </td>

                          <td>

                            {j.accepted_count}/{j.lines_count}

                          </td>

                          <td className="text-right text-nowrap">
                            {j.status === "ready" && (
                              <button
                                type="button"
                                className="btn btn-sm btn-success mr-1"
                                disabled={downloadingId === j.id}
                                title="Baixar PGR gerado"
                                onClick={() => handleDownload(j)}
                              >
                                {downloadingId === j.id ? (
                                  <i className="fas fa-spinner fa-spin" />
                                ) : (
                                  <>
                                    <i className="fas fa-download mr-1" />
                                    DOCX
                                  </>
                                )}
                              </button>
                            )}
                            <Link
                              to={`/jobs/${j.id}`}

                              className="btn btn-sm btn-primary mr-1"

                            >

                              <i className="fas fa-folder-open mr-1" />

                              Abrir

                            </Link>

                            <button

                              type="button"

                              className="btn btn-sm btn-outline-danger"

                              disabled={deletingId === j.id || j.status === "processing"}

                              title={

                                j.status === "processing"

                                  ? "Aguarde o processamento terminar"

                                  : "Excluir job"

                              }

                              onClick={() => removeJob(j)}

                            >

                              {deletingId === j.id ? (

                                <i className="fas fa-spinner fa-spin" />

                              ) : (

                                <i className="fas fa-trash" />

                              )}

                            </button>

                          </td>

                        </tr>

                      );

                    })}

                  {!loading && !jobs.length && (

                    <tr>

                      <td colSpan={5} className="text-center text-muted py-4">

                        Nenhum job ainda. Crie o primeiro para enviar campanha + PGR.

                      </td>

                    </tr>

                  )}

                </tbody>

              </table>

            </div>

          </div>

        </div>

      </section>

    </>

  );

}

