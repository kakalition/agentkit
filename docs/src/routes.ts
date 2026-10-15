import { index, route, type RouteConfig } from "@react-router/dev/routes"

export default [
  index("routes/landing.tsx"),
  route("guide", "routes/guide-index.tsx"),
  route("guide/:slug", "routes/guide-doc.tsx"),
  route("reference", "routes/reference-index.tsx"),
  route("reference/:slug", "routes/reference-doc.tsx"),
  route("*", "routes/not-found.tsx"),
] satisfies RouteConfig
