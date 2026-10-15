import { isRouteErrorResponse, Link, useRouteError } from "react-router"

import { Button } from "@/components/ui/button"

export function meta() {
  return [{ title: "Page not found · agentkit" }]
}

export function loader() {
  throw new Response("Not Found", { status: 404 })
}

function NotFoundScreen({ status }: { status: number }) {
  return (
    <div className="mx-auto flex w-full max-w-[88rem] flex-col items-center px-4 py-32 text-center sm:px-6">
      <p className="font-mono text-sm text-muted-foreground">{status}</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">
        {status === 404 ? "Page not found" : "Something went wrong"}
      </h1>
      <p className="mt-3 max-w-md text-muted-foreground">
        {status === 404
          ? "The page you are looking for does not exist or has moved."
          : "An unexpected error occurred. Please try again."}
      </p>
      <Button asChild size="lg" className="mt-8">
        <Link to="/guide/getting-started">Back to the docs</Link>
      </Button>
    </div>
  )
}

export function ErrorBoundary() {
  const error = useRouteError()
  const status = isRouteErrorResponse(error) ? error.status : 500
  return <NotFoundScreen status={status} />
}

export default function NotFound() {
  return <NotFoundScreen status={404} />
}
