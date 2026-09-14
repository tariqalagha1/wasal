"""Capture browser screenshots of the deployed HTTPS demo + verify public screens."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("/root/qms-v1/evidence/runs/qms-v1-customer-demo-deployment-001/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
BASE = "https://qms-demo.2.24.0.91.sslip.io"


with sync_playwright() as p:
    browser = p.chromium.launch()

    # Public display (read-only, no auth)
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.goto(f"{BASE}/display")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / "demo_display.png"), full_page=True)
    display_has_demo = "DEMO" in page.inner_text("body")
    display_text = page.inner_text("body")
    ctx.close()

    # Public calling screen (large text)
    ctx2 = browser.new_context(viewport={"width": 1600, "height": 900})
    page2 = ctx2.new_page()
    page2.goto(f"{BASE}/calling-screen")
    page2.wait_for_timeout(1200)
    page2.screenshot(path=str(OUT / "demo_calling_screen.png"))
    calling_has_demo = "DEMO" in page2.inner_text("body")
    ctx2.close()

    # Login (admin) — shows DEMO badge
    ctx3 = browser.new_context(viewport={"width": 1280, "height": 800})
    page3 = ctx3.new_page()
    page3.goto(f"{BASE}/login")
    page3.wait_for_timeout(800)
    page3.screenshot(path=str(OUT / "demo_login.png"))
    login_has_demo = "DEMO" in page3.inner_text("body")

    result = {
        "display_demo_label": display_has_demo,
        "calling_screen_demo_label": calling_has_demo,
        "login_demo_label": login_has_demo,
        "public_display_no_personal_data": all(
            x not in display_text for x in ["Abdullah", "Khalid", "Al-Otaibi", "Al-Harbi", "Guardian", "Student", "Booking"]
        ),
    }
    (OUT / "demo_ui_checks.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    browser.close()
    print(json.dumps(result, indent=2))
