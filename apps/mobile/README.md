# Eidovia — Mobile App

React Native / Expo app. Talks to the gateway on port `8000`.

## Start

```powershell
cd apps\mobile
npm install

# Set your backend URL in apps\mobile\.env:
# EXPO_PUBLIC_API_URL=http://<YOUR-PC-LAN-IP>:8000

$env:REACT_NATIVE_PACKAGER_HOSTNAME = "<YOUR-PC-LAN-IP>"
npx expo start --go --clear
```

Scan the QR with **Expo Go** on your phone (same Wi-Fi as PC).

> Find your LAN IP: run `ipconfig` → look for "IPv4 Address" under your Wi-Fi adapter.
