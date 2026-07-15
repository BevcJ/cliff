import { createBrowserRouter, Navigate } from "react-router-dom";

import { ForgotPasswordRoute } from "../features/auth/forgot-password-route";
import { LoginRoute } from "../features/auth/login-route";
import { ProtectedRoute } from "../features/auth/protected-route";
import { SetPasswordRoute } from "../features/auth/set-password-route";
import { InspectionLatestRoute } from "../features/inspection/routes/inspection-latest-route";
import { InspectionRoute } from "../features/inspection/routes/inspection-route";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/inspection" replace /> },
  { path: "/login", element: <LoginRoute /> },
  { path: "/forgot-password", element: <ForgotPasswordRoute /> },
  { path: "/set-password", element: <SetPasswordRoute /> },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/inspection", element: <InspectionLatestRoute /> },
      { path: "/inspection/:collectionDate", element: <InspectionRoute /> },
    ],
  },
  { path: "*", element: <Navigate to="/inspection" replace /> },
]);
