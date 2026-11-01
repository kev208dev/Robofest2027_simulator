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

    # The front gripper can capture more than one object at once.
    page.evaluate("window.__rfTest.reset()")
    assert page.evaluate("window.__rfTest.setPose(128,74.9,270)") is True
    page.evaluate("window.__rfTest.grab()")
    held = page.evaluate("window.__rfTest.getState().robot.held")
    assert "cat1" in held and "cat2" in held, held
    assert page.evaluate("window.__rfTest.getState().armLength") == 3
    print("Three-centimeter front arms and multi-object capture: OK")

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
    print("All regression tests passed.")
    browser.close()
