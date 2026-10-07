import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { lazy } from "react";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import { api } from "./api";

// Each page is its own bundle, loaded when first opened, so the login page
// does not wait for the charting library and the rest of the app.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const NewAssessment = lazy(() => import("./pages/NewAssessment"));
const History = lazy(() => import("./pages/History"));
const About = lazy(() => import("./pages/About"));
const Users = lazy(() => import("./pages/Users"));
const Monitoring = lazy(() => import("./pages/Monitoring"));

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