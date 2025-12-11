export const getConfig = () => {
  return window.__APP_CONFIG__ || {};
};

const baseURL = import.meta.env.VITE_BASE_URL || getConfig().BASE_URL;
const env = import.meta.env.VITE_APP_ENV || getConfig().APP_ENV;
const isApiServicesEnabled =
  import.meta.env.VITE_FEATURE_API_SERVICES === "true" ||
  getConfig().FEATURE_API_SERVICES === "true";

export const appEnv = {
  baseURL,
  isLocal: env === "local",
  isDev: env === "development",
  isStaging: env === "staging",
  isProd: env === "production",
  isApiServicesEnabled,
};
