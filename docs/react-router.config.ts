import type { Config } from "@react-router/dev/config"

import { DOC_PATHS } from "./src/lib/nav"

export default {
  appDirectory: "src",
  ssr: true,
  // Statically generate HTML for the landing page and every documentation page so
  // crawlers receive fully rendered markup.
  prerender: () => DOC_PATHS,
} satisfies Config
