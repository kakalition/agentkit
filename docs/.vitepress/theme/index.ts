import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme";
import "./style.css";

import BentoGrid from "./components/BentoGrid.vue";
import FeralGradient from "./components/FeralGradient.vue";
import GradientBackdrop from "./components/GradientBackdrop.vue";
import HeroOrb from "./components/HeroOrb.vue";
import Marquee from "./components/Marquee.vue";
import StatStrip from "./components/StatStrip.vue";
import Terminal from "./components/Terminal.vue";

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component("GradientBackdrop", GradientBackdrop);
    app.component("FeralGradient", FeralGradient);
    app.component("HeroOrb", HeroOrb);
    app.component("BentoGrid", BentoGrid);
    app.component("Terminal", Terminal);
    app.component("StatStrip", StatStrip);
    app.component("Marquee", Marquee);
  },
} satisfies Theme;
