import { createBrowserRouter, Navigate } from "react-router-dom";

import { LoginRoute } from "../features/auth/login-route";
import { ProtectedRoute } from "../features/auth/protected-route";
import { InspectionLatestRoute } from "../features/inspection/routes/inspection-latest-route";
import { InspectionRoute } from "../features/inspection/routes/inspection-route";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/inspection" replace /> },
  { path: "/login", element: <LoginRoute /> },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/inspection", element: <InspectionLatestRoute /> },
      { path: "/inspection/:collectionDate", element: <InspectionRoute /> },
    ],
  },
  { path: "*", element: <Navigate to="/inspection" replace /> },
]);
