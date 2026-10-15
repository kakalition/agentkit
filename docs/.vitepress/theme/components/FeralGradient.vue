<script setup lang="ts">
/**
 * Client-only React island that mounts the gradient element exported from
 * feralui.dev/gradients (see ./feral-gradient/runtime.gen.jsx). VitePress is a
 * Vue app, so we render nothing during SSR and mount React into the host once
 * the page is live. Decorative only — hidden from assistive tech.
 */
import { onBeforeUnmount, onMounted, ref } from "vue";

const host = ref<HTMLElement | null>(null);
let root: { render: (node: unknown) => void; unmount: () => void } | null = null;

onMounted(async () => {
  if (!host.value) return;
  // The exported element already honours prefers-reduced-motion (it freezes its
  // own animation), so we always mount it. If anything fails (no canvas, blocked
  // chunk) we keep the host's CSS fallback rather than break the page.
  try {
    const [{ createElement }, { createRoot }, mod] = await Promise.all([
      import("react"),
      import("react-dom/client"),
      // @ts-expect-error generated JSX module without type declarations
      import("./feral-gradient/runtime.gen.jsx"),
    ]);
    root = createRoot(host.value);
    root.render(createElement((mod as { default: unknown }).default));
  } catch (error) {
    console.warn("[agentkit] FeralUI gradient element failed to mount", error);
  }
});

onBeforeUnmount(() => {
  root?.unmount();
  root = null;
});
</script>

<template>
  <div ref="host" class="feral-gradient-host" aria-hidden="true" />
</template>
