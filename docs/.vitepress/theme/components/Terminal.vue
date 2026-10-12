<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

const lines = [
  "$ agentkit serve",
  "→ booting bootstrap:app …",
  "→ channels: webui, telegram",
  "→ scheduler: 3 jobs (cron + one-off)",
  "→ ready on http://127.0.0.1:8787",
];

const visible = ref<string[]>([]);
const current = ref("");
const caret = ref(true);
let lineTimer: ReturnType<typeof setTimeout> | undefined;
let charTimer: ReturnType<typeof setInterval> | undefined;
let blink: ReturnType<typeof setInterval> | undefined;

function play() {
  let index = 0;
  const nextLine = () => {
    if (index >= lines.length) {
      blink = setInterval(() => (caret.value = !caret.value), 520);
      return;
    }
    const line = lines[index++];
    let charIndex = 0;
    current.value = "";
    charTimer = setInterval(() => {
      current.value = line.slice(0, ++charIndex);
      if (charIndex >= line.length) {
        clearInterval(charTimer);
        visible.value.push(line);
        current.value = "";
        lineTimer = setTimeout(nextLine, 320);
      }
    }, 24);
  };
  nextLine();
}

onMounted(() => {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    visible.value = lines;
    return;
  }
  play();
});

onBeforeUnmount(() => {
  if (lineTimer) clearTimeout(lineTimer);
  if (charTimer) clearInterval(charTimer);
  if (blink) clearInterval(blink);
});
</script>

<template>
  <div class="ak-terminal">
    <div class="ak-terminal-bar">
      <span class="ak-dot ak-dot-r" /><span class="ak-dot ak-dot-y" /><span class="ak-dot ak-dot-g" />
      <span class="ak-terminal-title">nudge — agentkit</span>
    </div>
    <div class="ak-terminal-body">
      <div v-for="(line, i) in visible" :key="i" class="ak-line">{{ line }}</div>
      <div class="ak-line">
        <span>{{ current }}</span><span v-if="caret" class="ak-caret">▋</span>
      </div>
    </div>
  </div>
</template>
