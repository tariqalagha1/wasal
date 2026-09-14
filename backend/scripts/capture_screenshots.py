"""Capture browser screenshots of each QMS screen for certification evidence."""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("/root/qms-v1/evidence/runs/qms-v1-build-001/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
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

    # 1. Login screen
    page.goto(f"{BASE}/login")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(OUT / "01_login.png"))

    # 2. Reception / check-in
    login(page, "reception", "reception123")
    page.wait_for_timeout(800)
    page.screenshot(path=str(OUT / "02_checkin.png"), full_page=True)

    # 3. Cashier (WIN1)
    ctx2 = browser.new_context(viewport={"width": 1280, "height": 800})
    page2 = ctx2.new_page()
    page2.goto(f"{BASE}/login")
    page2.fill('input[placeholder="Username"]', "WIN1")
    page2.fill('input[placeholder="Password"]', "cashier123")
    page2.click('button:has-text("Sign in")')
    page2.wait_for_timeout(800)
    page2.screenshot(path=str(OUT / "03_cashier.png"), full_page=True)
    ctx2.close()

    # 4. Display (public)
    page3 = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page3.goto(f"{BASE}/display")
    page3.wait_for_timeout(800)
    page3.screenshot(path=str(OUT / "04_display.png"), full_page=True)
    page3.close()

    # 5. Calling screen (public, large text)
    page4 = browser.new_context(viewport={"width": 1600, "height": 900}).new_page()
    page4.goto(f"{BASE}/calling-screen")
    page4.wait_for_timeout(800)
    page4.screenshot(path=str(OUT / "05_calling_screen.png"))
    page4.close()

    # 6. Reports (admin)
    ctx5 = browser.new_context(viewport={"width": 1280, "height": 800})
    page5 = ctx5.new_page()
    page5.goto(f"{BASE}/login")
    page5.fill('input[placeholder="Username"]', "admin")
    page5.fill('input[placeholder="Password"]', "admin123")
    page5.click('button:has-text("Sign in")')
    page5.wait_for_timeout(300)
    page5.goto(f"{BASE}/reports")
    page5.wait_for_timeout(800)
    page5.screenshot(path=str(OUT / "06_reports.png"), full_page=True)

    # 7. Admin
    page5.goto(f"{BASE}/admin")
    page5.wait_for_timeout(500)
    page5.screenshot(path=str(OUT / "07_admin.png"), full_page=True)
    ctx5.close()

    browser.close()

print(f"Screenshots written to {OUT}")
