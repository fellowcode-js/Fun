"""Drive XON Studio in headless Chromium and save screenshots (chat, run code, design, agent, connect, mobile)."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from xon.design.render import Renderer  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791/#token=testtoken"
OUT = ROOT / "screenshots"


def wait_done(page, sel, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if page.evaluate(f"!document.querySelector('{sel}').disabled"):
            return
        page.wait_for_timeout(500)


with Renderer(1360, 860) as r:
    p = r._page
    p.set_viewport_size({"width": 1360, "height": 860})
    p.goto(URL)
    p.wait_for_timeout(1500)
    p.screenshot(path=str(OUT / "studio-home.png"))
    # chat: ask, stream, then run the returned code
    p.fill("#input", "Write a Python function is_palindrome(s) that ignores case and non-letters, then print(is_palindrome('A man, a plan, a canal: Panama')).")
    p.click("#send")
    p.wait_for_timeout(1500)
    wait_done(p, "#send")
    run = p.locator("[data-run]")
    if run.count():
        run.first.click()
        p.wait_for_selector(".runout", timeout=60000)
        p.wait_for_timeout(500)
    p.screenshot(path=str(OUT / "studio-chat.png"))
    # design
    p.click("nav button[data-view=design]")
    p.click("#design-go")
    p.wait_for_selector("#design-score:not([hidden])", timeout=120000)
    p.wait_for_timeout(1500)
    p.screenshot(path=str(OUT / "studio-design.png"))
    # agent
    p.click("nav button[data-view=agent]")
    p.click("#agent-go")
    t0 = time.time()
    while time.time() - t0 < 900:
        txt = p.inner_text("#agent-job")
        if "Done" in txt or "problems" in txt:
            break
        p.wait_for_timeout(2000)
    p.wait_for_timeout(500)
    p.screenshot(path=str(OUT / "studio-agent.png"), full_page=True)
    # connect
    p.click("nav button[data-view=connect]")
    p.wait_for_timeout(800)
    p.screenshot(path=str(OUT / "studio-connect.png"))
    # mobile
    p.set_viewport_size({"width": 390, "height": 844})
    p.click("nav button[data-view=chat]") if p.locator("nav button[data-view=chat]").is_visible() else None
    p.goto(URL.split("#")[0])
    p.wait_for_timeout(1200)
    p.screenshot(path=str(OUT / "studio-mobile.png"))
print("saved")
