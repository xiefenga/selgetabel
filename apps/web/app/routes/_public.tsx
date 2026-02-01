import { Outlet } from "react-router";
import { AuthLayout } from "~/components/layout/auth-layout";

const AuthPagesLayout = () => {
  return (
    <AuthLayout>
      <Outlet />
    </AuthLayout>
  );
}

export default AuthPagesLayout;
