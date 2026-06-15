import { Link } from "react-router-dom"

export function NotFoundPage() {
  return (
    <section aria-labelledby="page-title" className="text-center">
      <p className="text-sm font-semibold uppercase tracking-widest text-slate-500">404</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight" id="page-title">
        Page not found
      </h1>
      <p className="mx-auto mt-2 max-w-md text-slate-600">
        The page you were looking for does not exist or has moved.
      </p>
      <Link
        className="mt-6 inline-flex font-medium text-blue-700 underline-offset-4 hover:underline"
        to="/"
      >
        Go to the dashboard
      </Link>
    </section>
  )
}
