import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import NewAssessment from "./pages/NewAssessment";
import History from "./pages/History";
import About from "./pages/About";
import Login from "./pages/Login";
import Users from "./pages/Users";
import Monitoring from "./pages/Monitoring";
import { api } from "./api";

function ProtectedRoute({ children }) {
  const location = useLocation();

  if (!api.isAuthenticated()) {
    // Remember where the user was going (e.g. a link from a PR comment).
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public login page */}
        <Route path="/login" element={<Login />} />

        {/* Protected application */}
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewAssessment />} />
          <Route path="/history" element={<History />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/about" element={<About />} />
          <Route path="/users" element={<Users />} />
        </Route>

        {/* Unknown routes */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}