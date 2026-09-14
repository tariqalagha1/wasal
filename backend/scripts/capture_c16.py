"""C16 runtime evidence: offline disables write actions and shows a banner."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("/root/qms-v1/evidence/runs/qms-v1-build-001")
BASE = "http://localhost:5173"


def login(page, username, password):
    page.goto(f"{BASE}/login")
    page.fill('input[placeholder="Username"]', username)
    page.fill('input[placeholder="Password"]', password)
    page.click('button:has-text("Sign in")')
    page.wait_for_load_state("networkidle")


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()

    login(page, "WIN1", "cashier123")
    page.wait_for_timeout(1000)

    # Go offline.
    ctx.set_offline(True)
    page.wait_for_timeout(2500)

    banner = page.query_selector('.offline-banner')
    call_btn = page.locator('button:has-text("Call next")')
    disabled = call_btn.is_disabled()

    result = {
        "offline_banner_visible": banner is not None,
        "call_next_disabled_while_offline": disabled,
    }
    (OUT / "c16_offline_evidence.json").write_text(
        __import__("json").dumps(result, indent=2), encoding="utf-8"
    )

    page.screenshot(path=str(OUT / "screenshots" / "08_offline_cashier.png"))

    ctx.set_offline(False)
    browser.close()

    print(result)
    assert result["offline_banner_visible"] and result["call_next_disabled_while_offline"], "C16 failed"
    print("C16 PASS")
