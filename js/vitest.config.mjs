// ServerNode.tsx needs a DOM and a JSX transform; the .mjs suites run under
// node --test and stay out of vitest's way.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["**/*.test.tsx"],
  },
});
