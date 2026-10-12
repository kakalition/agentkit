<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { animate, type AnimationPlaybackControls } from "motion";

const orb = ref<HTMLElement | null>(null);
const ringA = ref<HTMLElement | null>(null);
const ringB = ref<HTMLElement | null>(null);
const controls: AnimationPlaybackControls[] = [];

onMounted(() => {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (orb.value) {
    controls.push(
      animate(
        orb.value,
        { y: [0, -16, 0], rotate: [0, 6, 0] },
        { duration: 7, repeat: Infinity, ease: "easeInOut" },
      ),
    );
  }
  if (ringA.value) {
    controls.push(animate(ringA.value, { rotate: 360 }, { duration: 40, repeat: Infinity, ease: "linear" }));
  }
  if (ringB.value) {
    controls.push(animate(ringB.value, { rotate: -360 }, { duration: 60, repeat: Infinity, ease: "linear" }));
  }
});

onBeforeUnmount(() => controls.forEach((control) => control.stop()));
</script>

<template>
  <div class="ak-orb-wrap">
    <div ref="ringA" class="ak-ring ak-ring-a" />
    <div ref="ringB" class="ak-ring ak-ring-b" />
    <div ref="orb" class="ak-orb">
      <div class="ak-orb-core" />
      <div class="ak-orb-gloss" />
    </div>
    <div class="ak-chip ak-chip-1">.memory()</div>
    <div class="ak-chip ak-chip-2">.skills()</div>
    <div class="ak-chip ak-chip-3">.knowledge()</div>
    <div class="ak-chip ak-chip-4">.stream()</div>
  </div>
</template>
