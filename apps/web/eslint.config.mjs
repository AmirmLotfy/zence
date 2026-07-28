// eslint-config-next 16 ships native flat config, so no FlatCompat shim is
// needed — and the shim in fact fails on this config with a circular-reference
// error while serializing the plugin object.
import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const config = [
  ...coreWebVitals,
  ...typescript,
  { ignores: [".next/**", "out/**", "node_modules/**"] },
];

export default config;
