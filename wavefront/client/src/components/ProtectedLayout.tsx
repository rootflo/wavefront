import { CURRENT_PATH_KEY, TOKEN_KEY } from "@app/lib/constants";
import { useEffect } from "react";
import { Outlet, useNavigate } from "react-router";

const ProtectedLayout = ({
  setAuthenticatedState,
}: {
  setAuthenticatedState: (authenticated: boolean) => void;
}) => {
  const navigate = useNavigate();

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    const currentPath = localStorage.getItem(CURRENT_PATH_KEY);

    if (!token) {
      setAuthenticatedState(false);
      navigate("/login");
      return;
    } else {
      setAuthenticatedState(true);
    }

    if (currentPath) {
      navigate(currentPath);
    }
  }, []);

  // Render child routes if authenticated
  return <Outlet />;
};

export default ProtectedLayout;
