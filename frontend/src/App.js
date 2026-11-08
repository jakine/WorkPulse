import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import Layout from "./components/Layout";
import CompanyPage from "./pages/CompanyPage";
import DashboardPage from "./pages/DashboardPage";
import DaysOffPage from "./pages/DaysOffPage";
import LoginPage from "./pages/LoginPage";
import PayPage from "./pages/PayPage";
import PayslipPage from "./pages/PayslipPage";
import StockPage from "./pages/StockPage";
import TeamsPage from "./pages/TeamsPage";
import TimesheetsPage from "./pages/TimesheetsPage";
import WorkersPage from "./pages/WorkersPage";
import WorkerPage from "./pages/WorkerPage";
import TeamPage from "./pages/TeamPage";
import PlanningPage from "./pages/PlanningPage";
import BoardPage from "./pages/BoardPage";
import ProjectPage from "./pages/ProjectPage";
import ProjectsPage from "./pages/ProjectsPage";
import SheetPage from "./pages/SheetPage";
import TimelinePage from "./pages/TimelinePage";
import WorkTypesPage from "./pages/WorkTypesPage";
import WorkflowSettingsPage from "./pages/WorkflowSettingsPage";
import WorkTimePage from "./pages/WorkTimePage";
import ReportsPage from "./pages/ReportsPage";
import ProtectedRoute from "./routes/ProtectedRoute";

function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/company" element={<CompanyPage />} />
            <Route path="/teams" element={<TeamsPage />} />
            <Route path="/teams/:id" element={<TeamPage />} />
            <Route path="/workers" element={<WorkersPage />} />
            <Route path="/workers/:id" element={<WorkerPage />} />
            <Route path="/planning" element={<PlanningPage />} />
            <Route path="/days-off" element={<DaysOffPage />} />
            <Route path="/timesheets" element={<TimesheetsPage />} />
            <Route path="/pay" element={<PayPage />} />
            <Route path="/pay/lines/:id" element={<PayslipPage />} />
            <Route path="/work-types" element={<WorkTypesPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:id" element={<ProjectPage />} />
            <Route path="/board" element={<BoardPage />} />
            <Route path="/sheet" element={<SheetPage />} />
            <Route path="/timeline" element={<TimelinePage />} />
            <Route path="/contracts" element={<Navigate to="/projects" replace />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/stock" element={<StockPage />} />
            <Route path="/settings/workflow" element={<WorkflowSettingsPage />} />
            <Route path="/settings/work-time" element={<WorkTimePage />} />
          </Route>
        </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
