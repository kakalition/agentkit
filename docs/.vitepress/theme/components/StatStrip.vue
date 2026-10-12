<script setup lang="ts">
import { onMounted, ref } from "vue";
import { animate, inView } from "motion";

const root = ref<HTMLElement | null>(null);

const stats = [
  { value: 155, suffix: "", label: "public exports" },
  { value: 279, suffix: "", label: "tests passing" },
  { value: 83, suffix: "%", label: "coverage" },
  { value: 40, suffix: "+", label: "docs pages" },
];

onMounted(() => {
  if (!root.value || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  inView(
    root.value,
    () => {
      root.value?.querySelectorAll<HTMLElement>("[data-count]").forEach((element, index) => {
        const target = Number(element.dataset.count ?? "0");
        animate(0, target, {
          duration: 1.4,
          delay: index * 0.08,
          ease: [0.22, 1, 0.36, 1],
          onUpdate: (latest) => {
            element.textContent = Math.round(latest).toString();
          },
        });
      });
      return () => {};
    },
    { amount: 0.4 },
  );
});
</script>

<template>
  <div ref="root" class="ak-stats">
    <div v-for="stat in stats" :key="stat.label" class="ak-stat">
      <div class="ak-stat-value"><span :data-count="stat.value">{{ stat.value }}</span><span class="ak-stat-suffix">{{ stat.suffix }}</span></div>
      <div class="ak-stat-label">{{ stat.label }}</div>
    </div>
  </div>
</template>
