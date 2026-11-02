"""Browser regression tests for the ROBOFEST 2027 simulator.

Run:
    pip install playwright
    python -m playwright install chromium
    python tests/regression.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_content(HTML, wait_until="load")

    # The front gripper can capture more than one object at once (two litter pieces
    # 6cm apart, both within the 3cm arm pocket).
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(112,22,270)") is True
    page.evaluate("window.__rfTest.grab()")
    held = page.evaluate("window.__rfTest.getState().robot.held")
    assert "litter1" in held and "litter2" in held and "litter3" not in held, held
    assert page.evaluate("window.__rfTest.getState().armLength") == 3
    # An object 26cm ahead is out of reach; one 14cm ahead (1.5cm past the nose) is captured.
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(108,60,0)") is True
    page.evaluate("window.__rfTest.grab()")
    assert page.evaluate("window.__rfTest.getState().robot.held") == ["cat1"]
    print("Three-centimeter front arms and multi-object capture: OK")

    # Start pose: just east of the start line, line directly ahead, facing west.
    page.evaluate("window.__rfTest.reset()")
    start = page.evaluate("window.__rfTest.getState().robot")
    assert (start["x"], start["y"], start["a"]) == (96.5, 37.5, 180), start
    assert page.evaluate("window.__rfTest.getState().sensors.front[3].p.x") > 82.95 + 1
    print("Start pose east of the start line: OK")

    # Each arrow-key press queues a smooth 15-degree turn.
    page.evaluate("window.__rfTest.reset()")
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    rotation = page.evaluate("window.__rfTest.getState().robot")
    assert rotation["autoAngle"] == 210, rotation
    page.evaluate("window.__rfTest.advance(3)")
    rotation = page.evaluate("window.__rfTest.getState().robot")
    assert abs(rotation["a"] - 210) < 0.6, rotation
    print("Incremental rotation: OK")

    # The session continues after 120s, and finishing reports overtime.
    page.evaluate("window.__rfTest.reset()")
    page.locator("#start").click()
    page.evaluate("window.__rfTest.advance(121)")
    page.locator("#finish").click()
    overtime = page.locator("#resultStatus").inner_text()
    assert "시간 초과" in overtime, overtime
    assert page.evaluate("window.__rfTest.getState().t") > 120
    print("Overtime result: OK")

    # Chassis is 20cm wide and 25cm long (wheels included in the width).
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.bodyOutsideFraction(12.5, 37.5, 0)") < 1e-7
    assert abs(page.evaluate("window.__rfTest.bodyOutsideFraction(0, 37.5, 0)") - 0.5) < 1e-7
    assert page.locator("header").inner_text().find("길이 25cm") >= 0
    print("Robot chassis size 20x25cm: OK")

    # Partial chassis overhang is legal; exactly 50% outside is not.
    page.evaluate("window.__rfTest.reset()")
    overhang = page.evaluate("window.__rfTest.bodyOutsideFraction(0.1, 30, 0)")
    assert 0.49 < overhang < 0.5, overhang
    assert page.evaluate("window.__rfTest.setPose(0.1, 30, 0)") is True
    assert page.evaluate("window.__rfTest.setPose(0, 30, 0)") is not True
    assert page.evaluate("window.__rfTest.setPose(91, 0.1, 90)") is True
    assert page.evaluate("window.__rfTest.setPose(91, 0, 90)") is not True
    # At x=161, facing east, the arm tip is at x>182; this must be allowed.
    assert page.evaluate("window.__rfTest.setPose(161, 65, 0)") is True
    # Rotated chassis near two adjacent field edges uses polygon area, not corners.
    assert page.evaluate("window.__rfTest.setPose(5, 5, 45)") is True
    print("Edge overhang and arm clearance: OK")

    # Both ends have seven sensors across the 15cm central chassis.
    page.evaluate("window.__rfTest.reset()")
    sensors = page.evaluate("window.__rfTest.getState().sensors")
    assert len(sensors["front"]) == 7 and len(sensors["back"]) == 7, sensors
    page.wait_for_function("document.getElementById('sensors').textContent.includes('/7')")
    assert page.locator("#sensors").inner_text().endswith("/7 · 0/7")
    # Align front array with the black vertical start line at x=82cm.
    assert page.evaluate("window.__rfTest.setPose(93.1, 37.5, 180)") is True
    sensor_hits = page.evaluate("window.__rfTest.getState().sensors")
    assert sum(bool(s["hit"]) for s in sensor_hits["front"]) == 7, sensor_hits
    assert sum(bool(s["hit"]) for s in sensor_hits["back"]) == 0, sensor_hits
    print("Dual seven-channel line sensors: OK")

    # A 3cm arm must not activate distant fixtures; near surfaces remain usable.
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(57,29,270)") is True
    assert page.evaluate("window.__rfTest.missionNear({shape:'rect',x:57,y:4,w:12,h:8})") is False
    assert page.evaluate("window.__rfTest.setPose(57,24,270)") is True
    assert page.evaluate("window.__rfTest.missionNear({shape:'rect',x:57,y:4,w:12,h:8})") is True
    assert page.evaluate("window.__rfTest.setPose(107,37.5,0)") is True
    assert page.evaluate("window.__rfTest.missionNear({shape:'circle',x:131,y:38,r:9})") is True
    print("Three-centimeter mission reach: OK")

    # Zones (user decision): Vet/Groomer/Litter Box are flat zones the robot can drive over;
    # an object counts once its footprint overlaps the zone. A cat that does not reach the
    # zone is "moved" only (5), one that overlaps it is in (10).
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.getState().score.parts[6][1]") == 0
    page.evaluate("window.__rfTest.placeObject('cat1',125,69.0)")
    assert page.evaluate("window.__rfTest.getState().score.parts[6][1]") == 5  # 0.4cm short of the zone
    page.evaluate("window.__rfTest.placeObject('cat1',125,70.0)")
    assert page.evaluate("window.__rfTest.getState().score.parts[6][1]") == 10  # overlaps the Vet zone
    page.evaluate("window.__rfTest.placeObject('cat2',50,70.0)")
    assert page.evaluate("window.__rfTest.getState().score.parts[7][1]") == 10
    page.evaluate("window.__rfTest.placeObject('litter3',123,5.4)")
    assert page.evaluate("window.__rfTest.getState().score.parts[2][1]") == 3
    # The robot may drive over a zone (no collision with the Vet strip).
    assert page.evaluate("window.__rfTest.setPose(127,62,0)") is True

    # Food: the dispenser task loads one piece at a time (10s default); the Pet Hotel is a
    # push-in: carried food drops in only when the arm tip reaches the 12cm bowl opening.
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(57,24,270)") is True
    page.keyboard.press("KeyM")
    page.evaluate("window.__rfTest.advance(5)")
    counts = page.evaluate("window.__rfTest.getState().foodCounts")
    assert counts["carried"] == 5 and counts["dispenser"] == 5, counts  # half-way through 10s
    page.evaluate("window.__rfTest.advance(6)")
    assert page.evaluate("window.__rfTest.getState().foodCounts")["carried"] == 10
    assert page.evaluate("window.__rfTest.forcePose(108.5,24,0)") is True  # beside the bowl
    page.keyboard.down("ArrowUp"); page.evaluate("window.__rfTest.advance(1.5)"); page.keyboard.up("ArrowUp")
    assert page.evaluate("window.__rfTest.getState().foodCounts")["hotel"] == 0
    assert page.evaluate("window.__rfTest.forcePose(100,38,0)") is True  # aligned with the bowl
    page.keyboard.down("ArrowUp"); page.evaluate("window.__rfTest.advance(1.5)"); page.keyboard.up("ArrowUp")
    assert page.evaluate("window.__rfTest.getState().foodCounts") == {"dispenser": 0, "carried": 0, "hotel": 10}
    page.keyboard.press("KeyM")
    assert page.evaluate("window.__rfTest.getState().task") is None  # the hotel is not a timed task
    print("Zones (overlap counts), per-piece dispenser, push-in Pet Hotel: OK")

    # Fixture contact is recorded as the scorecard's -10 'moved/damaged' penalty.
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(57,24,270)") is True
    page.keyboard.down("ArrowUp"); page.evaluate("window.__rfTest.advance(2)"); page.keyboard.up("ArrowUp")
    assert page.evaluate("window.__rfTest.getState().contacts") == ["food"]
    assert page.evaluate("window.__rfTest.getState().score.parts[11][1]") == -10
    print("Fixture contact penalty: OK")

    # Line tracing keeps the centre front sensor on the 1.9cm tape (half-width 0.95cm)
    # even when started 2cm off the line and 6 degrees skewed.
    for x0, a0 in [(80.6, 90), (79.5, 96), (84.5, 84)]:
        r = page.evaluate("""([x0,a0])=>{const T=window.__rfTest;T.reset();T.setPose(x0,30,a0);
            T.runSteps([{kind:'drive',trace:true,until:{bank:'front',hit:'경계',min:5},max:60,label:'trace'}]);
            for(let i=0;i<400;i++){T.advance(0.05);if(T.getState().routeIndex===-1)break}
            const s=T.getState();return {msg:s.routeMessage,cx:s.sensors.front[3].p.x,y:s.robot.y}}""", [x0, a0])
        assert r["msg"] == "custom", r
        assert abs(r["cx"] - 82) < 0.95, r
        assert r["y"] > 60, r
    print("Line tracing keeps the centre sensor on the tape: OK")

    # Saved route A (the only stored route), started from the UI button. Must finish within
    # 120s on the default layout: dog, cats (zones), food via line-traced dispenser + hotel
    # push, 3/3 litter in one push, Pet Toy, finish on the start line -> 100 points.
    assert page.evaluate("window.__rfTest.routes") == ["A"]
    page.locator("#restart").click()
    page.locator("#demo").click()
    result = page.evaluate("""() => {
        for (let i = 0; i < 2600; i++) {
            window.__rfTest.advance(0.1);
            const state = window.__rfTest.getState();
            if (state.result || (state.routeIndex === -1 && i > 4)) return state;
        }
        return window.__rfTest.getState();
    }""")
    assert result["result"], result["routeMessage"]
    assert result["t"] < 120, result["t"]
    assert result["score"]["total"] == 100, result["score"]
    assert result["foodCounts"] == {"dispenser": 0, "carried": 0, "hotel": 10}, result["foodCounts"]
    parts = {p[0].split(" (")[0]: p[1] for p in result["score"]["parts"]}
    assert parts["강아지 이동"] == 10 and parts["Pet Toy"] == 10, parts
    assert parts["흰 고양이"] == 10 and parts["주황 고양이"] == 10, parts
    assert parts["우편함 보존"] == 4, parts
    assert result["contacts"] == [], result["contacts"]
    assert not errors, errors
    print("Route A: %d/100 points, %.2fs" % (result["score"]["total"], result["t"]))
    print("All regression tests passed.")
    browser.close()
