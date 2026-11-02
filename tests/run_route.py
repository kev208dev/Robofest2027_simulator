"""Run a simulator route headlessly and print a step-by-step trace.

Usage:
    python tests/run_route.py [basic|user] [--lift H] [--seed-random] [--start X Y A]

Prints every route step with the simulated clock, aborts (with pose and reason),
the final score breakdown and the food/object state. Nothing is faked: the page
runs its own physics via window.__rfTest.advance().
"""
import argparse, json, random
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")

ap = argparse.ArgumentParser()
ap.add_argument("route", nargs="?", default="basic")


ap.add_argument("--seed-random", type=int, default=None, help="apply ±2cm random placement with this seed")
ap.add_argument("--start", nargs=3, type=float, default=None, metavar=("X", "Y", "A"))
ap.add_argument("--max-seconds", type=float, default=240)
ap.add_argument("--json", action="store_true")
args = ap.parse_args()

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_content(HTML, wait_until="load")
    page.evaluate("window.__rfTest.reset()")
    page.evaluate("name => window.__rfTest.startDemo(name)", args.route)
    if args.seed_random is not None:
        rnd = random.Random(args.seed_random)
        dev = {o: (round(rnd.uniform(-2, 2), 1), round(rnd.uniform(-2, 2), 1))
               for o in page.evaluate("window.__rfTest.getState().objects.map(o=>o.id)")}
        page.evaluate("d => window.__rfTest.applyDeviations(d)", dev)
        print("placement deviations (seed %d): %s" % (args.seed_random, dev))
    if args.start:
        x, y, a = args.start
        ok = page.evaluate("([x,y,a]) => window.__rfTest.forcePose(x,y,a)", [x, y, a])
        print("start pose override:", (x, y, a), "->", ok)
    last_step = None
    steps = int(args.max_seconds / 0.05)
    trace = []
    for i in range(steps):
        page.evaluate("window.__rfTest.advance(0.05)")
        st = page.evaluate("window.__rfTest.getState()")
        if st["routeStep"] != last_step and st["routeStep"] is not None:
            last_step = st["routeStep"]
            r = st["robot"]
            line = "t=%6.2fs  (%5.1f,%5.1f,%4.0f°) held=%-10s %s" % (st["t"], r["x"], r["y"], r["a"], ",".join(r["held"]) or "-", last_step)
            trace.append(line)
            print(line)
        if st["result"] or (st["routeIndex"] == -1 and i > 4):
            break
    st = page.evaluate("window.__rfTest.getState()")
    r = st["robot"]
    print("---")
    print("end: t=%.2fs pose=(%.1f,%.1f,%.0f°) routeMessage=%r" % (st["t"], r["x"], r["y"], r["a"], st["routeMessage"]))
    print("result:", "finished" if st["result"] else "NOT finished")
    print("score: %d/100" % st["score"]["total"])
    for name, pts, mx in st["score"]["parts"]:
        print("   %3d / %2d  %s" % (pts, mx, name))
    print("food:", st["foodCounts"], " contacts:", st["contacts"], " achievements:", {k: v for k, v in st["achievements"].items() if v})
    print("objects:", {o["id"]: (round(o["x"], 1), round(o["y"], 1), o.get("inside")) for o in st["objects"]})
    print("page errors:", errors or "none")
    print("last log lines:")
    for line in page.locator("#logs").inner_text().splitlines()[:8]:
        print("   ", line)
    if args.json:
        print(json.dumps(st, ensure_ascii=False)[:4000])
    browser.close()
