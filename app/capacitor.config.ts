import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.bmwmotorrad.ridefit',
  appName: 'BMW Motorrad',
  webDir: 'dist',
  // The backend is reached over Tailscale on plain HTTP (e.g. http://100.x.y.z:8090),
  // so cleartext must be allowed for the app to connect to the Mac-hosted server.
  server: {
    androidScheme: 'https',
    cleartext: true,
  },
};

export default config;
