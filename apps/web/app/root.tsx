import NiceModal from '@ebay/nice-modal-react';
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { isRouteErrorResponse, Links, Meta, Outlet, Scripts, ScrollRestoration } from "react-router";

import "./app.css";
import { Toaster } from '~/components/ui/sonner'

import type { Route } from "./+types/root";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: false,
    }
  }
})

export const links: Route.LinksFunction = () => [
  { rel: "icon", type: "image/svg+xml", href: "/logo.svg" },
];

export const Layout = ({ children }: { children: React.ReactNode }) => {
  return (
    <html lang="zh-CN">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <Meta />
        <Links />
      </head>
      <body className="h-screen w-screen overflow-hidden">
        <QueryClientProvider client={queryClient}>
          <NiceModal.Provider>
            {children}
          </NiceModal.Provider>
          <Toaster position="top-center" />
        </QueryClientProvider>
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}



export const ErrorBoundary = ({ error }: Route.ErrorBoundaryProps) => {
  let message = "Oops!";
  let details = "An unexpected error occurred.";
  let stack: string | undefined;

  if (isRouteErrorResponse(error)) {
    message = error.status === 404 ? "404" : "Error";
    details =
      error.status === 404
        ? "The requested page could not be found."
        : error.statusText || details;
  } else if (import.meta.env.DEV && error && error instanceof Error) {
    details = error.message;
    stack = error.stack;
  }

  return (
    <main className="pt-16 p-4 container mx-auto">
      <h1>{message}</h1>
      <p>{details}</p>
      {stack && (
        <pre className="w-full p-4 overflow-x-auto">
          <code>{stack}</code>
        </pre>
      )}
    </main>
  );
}

const App = () => {
  return <Outlet />;
}

export default App;
