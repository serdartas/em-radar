import { Route, Routes } from "react-router-dom"

import { AppLayout } from "@/components/layout/AppLayout"
import { DashboardPage } from "@/pages/DashboardPage"
import { JiraHelpPage } from "@/pages/JiraHelpPage"
import { NotFoundPage } from "@/pages/NotFoundPage"
import { ReportResultsPage } from "@/pages/ReportResultsPage"
import { ReportRunnerPage } from "@/pages/ReportRunnerPage"
import { ReportsListPage } from "@/pages/ReportsListPage"
import { SettingsPrivacyPage } from "@/pages/SettingsPrivacyPage"
import { SetupPage } from "@/pages/SetupPage"
import { SignalConfigGroupsPage } from "@/pages/SignalConfigGroupsPage"
import { SignalPackPage } from "@/pages/SignalPackPage"
import { SignalSettingsPage } from "@/pages/SignalSettingsPage"
import { SourceConnectionsPage } from "@/pages/SourceConnectionsPage"
import { TeamsPage } from "@/pages/TeamsPage"

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route element={<DashboardPage />} index />
        <Route element={<SetupPage />} path="setup" />
        <Route element={<SourceConnectionsPage />} path="connections" />
        <Route element={<JiraHelpPage />} path="help/jira" />
        <Route element={<TeamsPage />} path="teams" />
        <Route element={<SignalSettingsPage />} path="signals" />
        <Route element={<SignalConfigGroupsPage />} path="signals/groups" />
        <Route element={<SignalPackPage />} path="signals/import-export" />
        <Route element={<ReportRunnerPage />} path="reports/run" />
        <Route element={<ReportsListPage />} path="reports/results" />
        <Route element={<ReportResultsPage />} path="reports/results/:reportId" />
        <Route element={<SettingsPrivacyPage />} path="settings" />
        <Route element={<NotFoundPage />} path="*" />
      </Route>
    </Routes>
  )
}
