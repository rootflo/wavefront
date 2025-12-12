declare global {
  interface Window {
    __APP_CONFIG__: Record<string, string>;
  }
}
