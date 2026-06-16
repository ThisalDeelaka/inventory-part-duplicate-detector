import { NavLink, Outlet } from 'react-router-dom'

export default function Layout() {
  return (
    <div className="shell">
      <aside>
        <div className="brand"><span>PM</span><div>Part Master<small>Duplication Identifier</small></div></div>
        <nav>
          <NavLink to="/">Dashboard</NavLink>
          <NavLink to="/new-scan">New Scan</NavLink>
          <NavLink to="/load-test">Load Test</NavLink>
          <NavLink to="/data-security">Data Security</NavLink>
          <NavLink to="/future-ifs">Future IFS Integration</NavLink>
        </nav>
        <div className="notice">AI-assisted candidate detection.<br />Human review is required.</div>
      </aside>
      <main><Outlet /></main>
    </div>
  )
}
