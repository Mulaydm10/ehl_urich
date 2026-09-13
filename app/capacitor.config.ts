import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.bmwmotorrad.ridefit',
  appName: 'BMW Motorrad',
  webDir: 'dist',
  // The backend is reached over Tailscale on plain HTTP (e.g. http://100.x.y.z:8090).
  // Serving the web layer from https://localhost makes every such call mixed
  // content, which the WebView blocks outright, so the app is served from
  // http://localhost instead - still a secure context in Chromium, so geolocation
  // and speech keep working.
  server: {
    androidScheme: 'http',
    cleartext: true,
  },
};

export default config;
