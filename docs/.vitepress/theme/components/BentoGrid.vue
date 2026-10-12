<script setup lang="ts">
import { onMounted, ref } from "vue";
import { animate, inView, stagger } from "motion";

const grid = ref<HTMLElement | null>(null);

const items = [
  { icon: "🧩", title: "Declarative agents", body: "Compose persona, tools, memory and skills in one readable chain.", span: "a" },
  { icon: "🏗️", title: "An application", body: "Container, providers, facades, config sections, a CLI — not a script.", span: "b" },
  { icon: "⚡", title: "Streaming", body: "Token-by-token output to any channel, with usage recorded.", span: "c" },
  { icon: "🧠", title: "Memory & RAG", body: "Durable facts and an embedding-indexed knowledge base.", span: "d" },
  { icon: "🛡️", title: "Safety", body: "Approvals, clarification, moderation, PII and a hash-chained audit log.", span: "e" },
  { icon: "🔌", title: "MCP & A2A", body: "Consume MCP toolsets; speak the A2A protocol.", span: "f" },
];

onMounted(() => {
  if (!grid.value || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  inView(
    grid.value,
    () => {
      const cards = grid.value?.querySelectorAll(".ak-bento-card");
      if (cards) {
        animate(cards, { opacity: [0, 1], y: [26, 0], scale: [0.98, 1] }, { duration: 0.7, delay: stagger(0.07), ease: [0.22, 1, 0.36, 1] });
      }
      return () => {};
    },
    { amount: 0.2 },
  );
});
</script>

<template>
  <div ref="grid" class="ak-bento">
    <article v-for="item in items" :key="item.title" :class="`ak-bento-card ak-span-${item.span}`">
      <div class="ak-bento-icon">{{ item.icon }}</div>
      <h3>{{ item.title }}</h3>
      <p>{{ item.body }}</p>
    </article>
  </div>
</template>
