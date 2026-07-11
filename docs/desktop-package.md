# Desktop Packaging

The desktop app packages the Web UI with an Electron shell and a Python backend artifact. Desktop changes may affect `apps/dsa-desktop/`, `apps/dsa-web/`, desktop scripts, backend packaging scripts, and release workflows.

Build the Web app first, then package desktop:

```bash
cd apps/dsa-web
npm run build

cd ../dsa-desktop
npm run build
```

Desktop packages must include required backend dependencies. Optional integrations should be validated during backend packaging if included in `requirements.txt`. Roll back by reverting the packaging change and rebuilding artifacts.
