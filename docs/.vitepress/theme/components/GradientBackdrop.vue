<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { animate, type AnimationPlaybackControls } from "motion";

const blobs = ref<Array<HTMLElement | null>>([]);
const controls: AnimationPlaybackControls[] = [];

onMounted(() => {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const paths = [
    { x: [0, 140, -80, 0], y: [0, -90, 70, 0], scale: [1, 1.18, 0.94, 1], duration: 26 },
    { x: [0, -120, 90, 0], y: [0, 80, -60, 0], scale: [1, 0.9, 1.2, 1], duration: 32 },
    { x: [0, 90, -110, 0], y: [0, 60, 90, 0], scale: [1, 1.12, 0.98, 1], duration: 38 },
    { x: [0, -70, 120, 0], y: [0, -70, 50, 0], scale: [1, 1.24, 0.9, 1], duration: 44 },
    { x: [0, 60, -40, 0], y: [0, 50, -70, 0], scale: [1, 0.96, 1.1, 1], duration: 30 },
  ];
  blobs.value.forEach((element, index) => {
    if (!element) return;
    const cfg = paths[index % paths.length];
    controls.push(
      animate(
        element,
        { x: cfg.x, y: cfg.y, scale: cfg.scale },
        { duration: cfg.duration, repeat: Infinity, ease: "easeInOut" },
      ),
    );
  });
});

onBeforeUnmount(() => controls.forEach((control) => control.stop()));
</script>

<template>
  <div class="ak-backdrop" aria-hidden="true">
    <span
      v-for="i in 5"
      :key="i"
      :ref="(el) => (blobs[i - 1] = el as HTMLElement)"
      :class="`ak-blob ak-blob-${i}`"
    />
  </div>
</template>
