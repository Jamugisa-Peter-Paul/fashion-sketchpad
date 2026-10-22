import type { NextConfig } from "next";

// Static export: the `out/` folder is what Capacitor wraps into the Android app.
const nextConfig: NextConfig = {
  output: "export",
  // /style -> out/style/index.html, which the Capacitor webview resolves on reload.
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
