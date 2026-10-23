# The app (Next.js + Capacitor)

`app/` is a Next.js static export wrapped by Capacitor into an Android app. The phone talks to the
gateway only (`NEXT_PUBLIC_API_URL`, which can be changed on the login screen). Images are fetched with
the access code, so it never goes into URLs.

## Screens

| Route | What |
|---|---|
| `/login` | Access code (one of the gateway's `APP_TOKENS`) and the server address |
| `/` | New design, continue draft, recent designs |
| `/new` | Draw or upload · Women/Men/Kids · body type (ungenerated templates are greyed out) · garment |
| `/sketch` | Drawing canvas over the body outline: Front/Back(/Side), pen with stylus pressure, eraser, sizes, undo/redo/clear, pinch zoom |
| `/upload` | Photo or gallery for front and back, cleaned preview over the body, drag/pinch placement |
| `/style` | Colour (+custom, prints), fabric, fit, buttons, stitching, scene, mannequin finish, extra notes |
| `/generate` | Progress, front and back results, New variation, Change colour, Edit, Save, Share, render history |
| `/designs`, `/design?id=` | Gallery, design detail, rename, delete, tweak style, edit sketch |
| `/settings` | Server status, clear draft, sign out |

The current design is a **draft** in IndexedDB (`src/lib/draft.ts`): choices, stroke vectors for drawn
sketches, and the cleaned-upload ids and placements. It's saved after every change, so closing the app
or a crash never loses a sketch. Photos for upload mode are kept in IndexedDB too, so expired uploads can
be re-cleaned automatically. The catalog and body outlines are cached, so you can start a design and draw
offline. Generating needs the server.

## Develop in the browser

You need Node 22+. In one terminal, start the gateway (with the real ComfyUI, or the fake one, see the
README). Then:

```powershell
cd app
npm install
copy .env.example .env.local      # NEXT_PUBLIC_API_URL=http://127.0.0.1:8190 for a local gateway
npm run dev                       # http://localhost:3000
npm test                          # unit tests (vitest)
npm run lint; npm run typecheck
```

Chrome DevTools' device toolbar (Ctrl+Shift+M) with a touch device gives a good phone preview. Stylus
pressure can only be tested on a real device.

## Build an Android APK (Windows)

Prerequisites: Android Studio with an Android SDK (already installed), and JDK 21. Android Studio's bundled
JBR is fine. Capacitor 8 does not build with JDK 17, which is what your `JAVA_HOME` currently points to.

1. Set the server the app should use by default:

   ```powershell
   cd app
   copy .env.example .env.local      # NEXT_PUBLIC_API_URL=https://fashion-api.ucu-dct.org
   ```

2. Build the debug APK in one step:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\build-apk.ps1
   ```

   This runs `npm run build` (writes the static site to `out/`), `npx cap sync android` (copies it into
   `android/` and updates plugins), and `gradlew assembleDebug`, with `JAVA_HOME` pointed at Android
   Studio's JBR. The APK ends up at `app\android\app\build\outputs\apk\debug\app-debug.apk`.

3. Install it:
   - USB, with developer options and USB debugging on: `adb install -r app\android\app\build\outputs\apk\debug\app-debug.apk`
     (`adb` is in `%LOCALAPPDATA%\Android\Sdk\platform-tools`).
   - Or copy the APK to the phone and open it, allowing "Install unknown apps" for the file manager.

To do it from Android Studio instead: `npm run build`, `npx cap sync android`, `npx cap open android`,
then **Build > Build App Bundle(s) / APK(s) > Build APK(s)**. Use Run (▶) to install on a connected
phone or an emulator.

`npx cap add android` has already been run, and `app/android/` is committed. Only run it again if you
delete that folder. After any change to the web code, rebuild and sync (step 2). After adding a Capacitor
plugin, run `npx cap sync android`.

### Testing against a plain-http gateway on the LAN

Android blocks `http://` by default. To point a test build at `http://100.111.145.48:8190` (which also needs
the gateway to listen on `0.0.0.0`, or an SSH tunnel), build with
`scripts\build-apk.ps1 -AllowHttp` and enter that address under **Server** on the login screen. Normal
builds use the HTTPS Cloudflare address and don't need this.

### App icon and name

The name is `appName` in `capacitor.config.ts` and `android/app/src/main/res/values/strings.xml`. To
replace the default Capacitor icon, put a 1024×1024 `icon.png` (and optionally `splash.png`) in
`app/assets/` and run `npx @capacitor/assets generate --android`.

### Release builds

Debug APKs are fine for personal use. For a signed release, create a keystore once (keep it out of the
repo) and use **Build > Generate Signed App Bundle / APK** in Android Studio.

## Where things are saved on the phone

| What | Where |
|---|---|
| Access code, server address | Capacitor Preferences |
| Draft, photos, cached catalog and outlines | IndexedDB in the app's webview |
| Saved renders (Save button) | `Documents/FashionSketchpad/` (asks for storage permission only on Android 10 and older) |
| Shared renders | Through the system share sheet (WhatsApp, Drive, Photos, …) |

Designs and renders themselves live on the server (`DATA_DIR`), so they appear on any phone signed in to
the same gateway.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Can't reach the server" | Open `https://fashion-api.ucu-dct.org/api/health` in the phone's browser. If Cloudflare shows a challenge page, add the WAF skip rule (see DEPLOY.md) |
| "That access code isn't valid" | The code must be in `APP_TOKENS` on the server. Restart `fashion-gateway` after editing |
| Gradle: `The filename, directory name, or volume label syntax is incorrect` | `app/android/local.properties` must use forward slashes: `sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk` (Android Studio writes it correctly when you open the project) |
| Gradle: `Unsupported class file major version` or `requires Java 21` | Use `scripts\build-apk.ps1`, or set `JAVA_HOME` to `C:\Program Files\Android\Android Studio\jbr` |
| The app shows an old version | Rebuild and run `npx cap sync android` before building the APK |
| Stylus pressure has no effect | Only `pointerType: pen` gives pressure. Fingers draw at a constant width by design |
