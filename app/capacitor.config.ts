import type { CapacitorConfig } from "@capacitor/cli";

// Set CAP_ALLOW_HTTP=1 when building an APK that talks to a plain-http gateway on the LAN
// (e.g. http://10.4.18.27:8190). The normal build uses https://fashion-api.ucu-dct.org.
const allowHttp = process.env.CAP_ALLOW_HTTP === "1";

const config: CapacitorConfig = {
  appId: "org.ucudct.fashionsketchpad",
  appName: "Fashion Sketchpad",
  webDir: "out",
  server: {
    androidScheme: "https",
    ...(allowHttp ? { cleartext: true } : {}),
  },
  android: {
    allowMixedContent: allowHttp,
  },
};

export default config;
