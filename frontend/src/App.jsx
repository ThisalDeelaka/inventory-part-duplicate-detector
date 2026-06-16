import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import NewScan from './pages/NewScan'
import ScanResults from './pages/ScanResults'
import Warnings from './pages/Warnings'
import LoadTest from './pages/LoadTest'
import FutureIFSIntegration from './pages/FutureIFSIntegration'
import DataSecurity from './pages/DataSecurity'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new-scan" element={<NewScan />} />
          <Route path="/scans/:id" element={<ScanResults />} />
          <Route path="/scans/:id/warnings" element={<Warnings />} />
          <Route path="/load-test" element={<LoadTest />} />
          <Route path="/data-security" element={<DataSecurity />} />
          <Route path="/future-ifs" element={<FutureIFSIntegration />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
