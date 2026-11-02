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
    # 6cm apart, both within the 3cm arm pocket). The Vet is a solid structure, so the
    # old pose over it is now (correctly) rejected.
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(128,74.9,270)") is not True
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

    # Walled structures: a cat on the floor cannot be pushed into the Vet; the Pet Hotel
    # task refuses when the arm is not centred on the 12cm bowl opening; food moves one
    # piece at a time so the 120s snapshot only counts pieces moved by then.
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(122,46,90)") is not True  # hotel blocks
    # Capture the white cat from the west (lateral +5cm in the pocket), then carry it to
    # the Groomer wall facing south. In the current layout a 25cm chassis cannot spin
    # between the hotel and the Vet, so the Groomer is used for this geometry check.
    assert page.evaluate("window.__rfTest.setPose(108,55,0)") is True
    page.evaluate("window.__rfTest.grab()")
    assert page.evaluate("window.__rfTest.getState().robot.held") == ["cat1"]
    assert page.evaluate("window.__rfTest.forcePose(53.5,50,90)") is True
    page.keyboard.down("ArrowUp"); page.evaluate("window.__rfTest.advance(3)"); page.keyboard.up("ArrowUp")
    st = page.evaluate("window.__rfTest.getState()")
    cat1 = next(o for o in st["objects"] if o["id"] == "cat1")
    assert cat1["y"] < 72 - 2.6 + 0.2 and cat1["inside"] is None, cat1  # stopped at the wall
    assert st["robot"]["y"] < 56, st["robot"]  # robot could not push the cat through the wall
    assert st["score"]["parts"][6][1] == 5, st["score"]["parts"][6]  # moved, not in the Vet
    page.evaluate("window.__rfTest.grab()")  # release in front of the wall -> still moved only
    assert page.evaluate("window.__rfTest.getState().score.parts[6][1]") == 5
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(106.5,24,0)") is True
    page.keyboard.press("KeyM")
    assert page.evaluate("window.__rfTest.getState().task") is None  # no food carried yet
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(57,24,270)") is True
    page.keyboard.press("KeyM")
    page.evaluate("window.__rfTest.advance(6)")
    counts = page.evaluate("window.__rfTest.getState().foodCounts")
    assert counts["carried"] == 5 and counts["dispenser"] == 5, counts  # half-way through 12s
    page.evaluate("window.__rfTest.advance(7)")
    assert page.evaluate("window.__rfTest.getState().foodCounts")["carried"] == 10
    assert page.evaluate("window.__rfTest.forcePose(106.5,24,0)") is True  # beside the bowl, 14cm off
    page.keyboard.press("KeyM")
    assert page.evaluate("window.__rfTest.getState().task") is None
    assert page.evaluate("window.__rfTest.forcePose(106.5,38,0)") is True
    page.keyboard.press("KeyM")
    assert page.evaluate("window.__rfTest.getState().task.id") == "hotel"
    print("Walled structures, bowl alignment, per-piece food transfer: OK")

    # Lift scaffold: with an assumed lift the held orange cat is placed inside the Groomer.
    page.evaluate("window.__rfTest.reset()")
    page.fill("#liftMax", "8"); page.evaluate("document.activeElement.blur()")  # keys go to the page, not the input
    assert page.evaluate("window.__rfTest.setPose(148,56,180)") is True
    page.evaluate("window.__rfTest.grab()")
    assert page.evaluate("window.__rfTest.getState().robot.held") == ["cat2"]
    assert page.evaluate("window.__rfTest.forcePose(53.5,50,90)") is True
    page.keyboard.press("KeyL"); page.evaluate("window.__rfTest.advance(4)")
    assert page.evaluate("window.__rfTest.getState().lift.height") == 8
    page.keyboard.down("ArrowUp"); page.evaluate("window.__rfTest.advance(3)"); page.keyboard.up("ArrowUp")
    st = page.evaluate("window.__rfTest.getState()")
    assert 59 < st["robot"]["y"] < 60, st["robot"]  # chassis nose stopped at the wall (y=72)
    page.evaluate("window.__rfTest.grab()")
    cat2 = next(o for o in page.evaluate("window.__rfTest.getState().objects") if o["id"] == "cat2")
    assert cat2["inside"] == "groomer" and cat2["y"] >= 72, cat2
    assert page.evaluate("window.__rfTest.getState().score.parts[7][1]") == 10
    page.fill("#liftMax", "0"); page.evaluate("document.activeElement.blur()")
    print("Lift scaffold (assumed lift) places cat inside Groomer: OK")

    # Fixture contact is recorded as the scorecard's -10 'moved/damaged' penalty.
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(57,24,270)") is True
    page.keyboard.down("ArrowUp"); page.evaluate("window.__rfTest.advance(2)"); page.keyboard.up("ArrowUp")
    assert page.evaluate("window.__rfTest.getState().contacts") == ["food"]
    assert page.evaluate("window.__rfTest.getState().score.parts[11][1]") == -10
    print("Fixture contact penalty: OK")

    # Verify the reference route on the default object layout.
    # #newTrial lives inside the hidden results dialog here (reset() closed it), so
    # use the always-visible restart button, which calls the same reset().
    page.locator("#restart").click()
    page.locator("#demo").click()
    result = page.evaluate("""() => {
        let carriedFoodSeen = false;
        for (let i = 0; i < 2300; i++) {
            window.__rfTest.advance(0.1);
            const state = window.__rfTest.getState();
            carriedFoodSeen ||= state.foodCounts.carried === 10;
            if (state.result || (state.routeIndex === -1 && i > 4))
                return {...state, carriedFoodSeen};
        }
        return {...window.__rfTest.getState(), carriedFoodSeen};
    }""")
    assert result["result"], result["routeMessage"]
    assert result["score"]["total"] == 61, result["score"]
    assert result["carriedFoodSeen"], "Food never travelled with the robot"
    assert result["foodCounts"] == {"dispenser": 0, "carried": 0, "hotel": 10}, result["foodCounts"]
    page.wait_for_function("document.getElementById('foodStatus').textContent.trim() === '0 / 0 / 10'")
    assert page.locator("#foodStatus").inner_text().strip() == "0 / 0 / 10"
    print("Food dispenser -> robot -> hotel: 10 pieces, 20 points")
    assert not errors, errors
    print("Default reference route: 61/100 points, %.2fs" % result["t"])

    # User-proposed sensor-based route (start line -> dog -> park -> line trace -> cats ->
    # groomer pivot -> litter box -> pet toy -> finish) must complete within 120s on the
    # default layout without a lift. Cats stay "moved only" (walls) and one litter piece
    # is out of the chassis width in the current layout, so the honest score is 67.
    page.evaluate("window.__rfTest.startDemo('user')")
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
    assert result["score"]["total"] >= 65, result["score"]
    parts = {p[0].split(" (")[0]: p[1] for p in result["score"]["parts"]}
    assert parts["강아지 이동"] == 10 and parts["Pet Toy"] == 10, parts
    assert result["contacts"] == [], result["contacts"]
    assert not errors, errors
    print("User-proposed route: %d/100 points, %.2fs" % (result["score"]["total"], result["t"]))
    print("All regression tests passed.")
    browser.close()
