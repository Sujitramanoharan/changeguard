import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import NewAssessment from "./pages/NewAssessment";
import History from "./pages/History";
import About from "./pages/About";
import Login from "./pages/Login";
import { api } from "./api";

function ProtectedRoute({ children }) {
  if (!api.isAuthenticated()) {
    return <Navigate to="/login" replace />;
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
          <Route path="/about" element={<About />} />
        </Route>

        {/* Unknown routes */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}