<script setup lang="ts">
const keywords = [
  "Agent.make()",
  "Provider",
  "Memory",
  "SkillRegistry",
  "KnowledgeBase",
  "Compactor",
  "StateGraph",
  "Supervisor",
  "ModelRouter",
  "Streaming",
  "Approvals",
  "Moderation",
  "PromptRegistry",
  "Budget",
  "EvalSuite",
  "Sandbox",
  "MCP",
  "A2A",
  "DBOS",
  "genai_prices",
  "pydantic_evals",
];
</script>

<template>
  <div class="ak-marquee" aria-hidden="true">
    <div class="ak-marquee-track">
      <span v-for="(word, i) in [...keywords, ...keywords]" :key="i" class="ak-marquee-item">{{ word }}</span>
    </div>
  </div>
</template>
