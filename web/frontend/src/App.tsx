import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { CentralModelPage } from './pages/CentralModelPage'
import { ClientsPage } from './pages/ClientsPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { HistoryPage } from './pages/HistoryPage'
import { IntrusionPage } from './pages/IntrusionPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { OverviewPage } from './pages/OverviewPage'
import { PerformancePage } from './pages/PerformancePage'
import { SdnPage } from './pages/SdnPage'
import { SecurityPage } from './pages/SecurityPage'
import { SettingsPage } from './pages/SettingsPage'
import { TrainingPage } from './pages/TrainingPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="central-model" element={<CentralModelPage/>}/>
          <Route path="training" element={<TrainingPage />} />
          <Route path="clients" element={<ClientsPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="datasets" element={<DatasetsPage />} />
          <Route path="performance" element={<PerformancePage />} />
          <Route path="encryption" element={<Navigate to="/security" replace />} />
          <Route path="security" element={<SecurityPage />} />
          <Route path="intrusion" element={<IntrusionPage />} />
          <Route path="sdn" element={<SdnPage />} />
          <Route path="ips" element={<Navigate to="/security" replace />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
