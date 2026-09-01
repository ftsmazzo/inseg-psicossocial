import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./api";
import AppLayout from "./layout/AppLayout";
import Login from "./pages/Login";
import Jobs from "./pages/Jobs";
import JobWorkspace from "./pages/JobWorkspace";

function Private({ children }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <Private>
            <AppLayout />
          </Private>
        }
      >
        <Route index element={<Jobs />} />
        <Route path="jobs/:id" element={<JobWorkspace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
