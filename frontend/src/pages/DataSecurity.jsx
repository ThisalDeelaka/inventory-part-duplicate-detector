export default function DataSecurity() {
  return (
    <>
      <header>
        <div>
          <p className="eyebrow">Sensitive ERP data</p>
          <h1>Data security mode</h1>
          <p>Practical protections for CSV exports from real ERP environments.</p>
        </div>
      </header>
      <section className="panel prose">
        <h2>What this demo does now</h2>
        <p>The detector processes CSV files locally in the backend. It does not call external AI APIs and it does not persist the uploaded raw CSV file.</p>
        <h2>Sensitive Data Mode</h2>
        <p>Uploads receive a security transparency summary, SHA-256 file fingerprint, and warnings for possible sensitive patterns such as email-like values, phone-like values, project/work-order references, and supplier references.</p>
        <h2>What is stored</h2>
        <p>Scan summaries, candidate pairs, scores, explanations, warnings, and reviewer feedback are stored for review. The original CSV file is not stored.</p>
        <h2>Production controls still needed</h2>
        <p>Use SSO, authorization, audit logging, PostgreSQL, encrypted storage, network policies, retention/deletion workflows, and monitoring before handling live IFS ERP data at scale.</p>
      </section>
    </>
  )
}
