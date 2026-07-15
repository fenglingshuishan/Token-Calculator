# E2E Tests

Playwright end-to-end tests for the Prompt Optimization Workstation.

**Prerequisites:**
```bash
npm install        # installs playwright
npx playwright install chromium
```

**Running:**
```bash
# Start the server first
.venv/Scripts/python run.py

# Then run tests (from project root)
node tests/e2e/e2e-test.mjs
```

Screenshots are written to `screenshots/e2e-*.png` (git-ignored).
