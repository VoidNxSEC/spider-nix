"""
Human behavioral simulation for Playwright.

Layer 3 anti-detection: mouse trajectory, keystroke dynamics, scroll curves.
Anti-bot systems correlate timing entropy — random.gauss() throughout, not uniform().
"""

import asyncio
import math
import random
from typing import Literal

from playwright.async_api import ElementHandle, Page


# Adjacent keys on a QWERTY layout for realistic typo simulation.
_ADJACENT: dict[str, list[str]] = {
    "a": ["q", "w", "s", "z"],
    "b": ["v", "g", "h", "n"],
    "c": ["x", "d", "f", "v"],
    "d": ["s", "e", "r", "f", "c", "x"],
    "e": ["w", "r", "d", "s"],
    "f": ["d", "r", "t", "g", "v", "c"],
    "g": ["f", "t", "y", "h", "b", "v"],
    "h": ["g", "y", "u", "j", "n", "b"],
    "i": ["u", "o", "k", "j"],
    "j": ["h", "u", "i", "k", "n", "m"],
    "k": ["j", "i", "o", "l", "m"],
    "l": ["k", "o", "p"],
    "m": ["n", "j", "k"],
    "n": ["b", "h", "j", "m"],
    "o": ["i", "p", "l", "k"],
    "p": ["o", "l"],
    "q": ["w", "a"],
    "r": ["e", "t", "f", "d"],
    "s": ["a", "w", "e", "d", "x", "z"],
    "t": ["r", "y", "g", "f"],
    "u": ["y", "i", "j", "h"],
    "v": ["c", "f", "g", "b"],
    "w": ["q", "e", "s", "a"],
    "x": ["z", "s", "d", "c"],
    "y": ["t", "u", "h", "g"],
    "z": ["a", "s", "x"],
    "0": ["9", "-"],
    "1": ["2", "q"],
    "2": ["1", "3", "w"],
    "3": ["2", "4", "e"],
    "4": ["3", "5", "r"],
    "5": ["4", "6", "t"],
    "6": ["5", "7", "y"],
    "7": ["6", "8", "u"],
    "8": ["7", "9", "i"],
    "9": ["8", "0", "o"],
    ".": [",", "/", "l"],
    "@": ["a"],
}


def _bezier_points(
    x0: float, y0: float, x1: float, y1: float, n: int = 40, overshoot: bool = False
) -> list[tuple[float, float]]:
    """
    Cubic Bezier path from (x0,y0) to (x1,y1) with randomized control points.
    Optionally adds a slight overshoot past the target.
    """
    dx = x1 - x0
    dy = y1 - y0
    dist = math.hypot(dx, dy)

    # Control points: push off-center for a natural arc
    cp1x = x0 + dx * random.uniform(0.15, 0.35) + random.gauss(0, dist * 0.08)
    cp1y = y0 + dy * random.uniform(0.15, 0.35) + random.gauss(0, dist * 0.08)
    cp2x = x0 + dx * random.uniform(0.65, 0.85) + random.gauss(0, dist * 0.05)
    cp2y = y0 + dy * random.uniform(0.65, 0.85) + random.gauss(0, dist * 0.05)

    # Overshoot: target slightly past the destination, then snap back
    ex, ey = x1, y1
    if overshoot:
        overshoot_px = random.uniform(4, 14)
        angle = math.atan2(dy, dx)
        ex = x1 + math.cos(angle) * overshoot_px
        ey = y1 + math.sin(angle) * overshoot_px

    points: list[tuple[float, float]] = []
    for i in range(n):
        t = i / (n - 1)
        u = 1 - t
        x = u**3 * x0 + 3 * u**2 * t * cp1x + 3 * u * t**2 * cp2x + t**3 * ex
        y = u**3 * y0 + 3 * u**2 * t * cp1y + 3 * u * t**2 * cp2y + t**3 * ey
        # Micro-jitter — imperceptible tremor present in all human movement
        x += random.gauss(0, 0.4)
        y += random.gauss(0, 0.4)
        points.append((x, y))

    if overshoot:
        # Snap back to real target in a short arc
        snap_n = max(5, n // 8)
        for i in range(snap_n):
            t = i / (snap_n - 1)
            px = ex + (x1 - ex) * t + random.gauss(0, 0.3)
            py = ey + (y1 - ey) * t + random.gauss(0, 0.3)
            points.append((px, py))

    return points


async def human_move_to(
    page: Page,
    target: ElementHandle | str,
    *,
    overshoot: bool = True,
    speed: Literal["slow", "normal", "fast"] = "normal",
) -> None:
    """
    Move the mouse to a target element along a Bezier curve.

    speed:  slow ≈ 600ms, normal ≈ 300ms, fast ≈ 120ms total traversal.
    """
    speed_ms = {"slow": 600, "normal": 300, "fast": 120}[speed]

    if isinstance(target, str):
        el = await page.query_selector(target)
        if el is None:
            return
        target = el

    box = await target.bounding_box()
    if box is None:
        return

    dest_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    dest_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)

    current = await page.evaluate("() => ({ x: window._lastMouseX || 0, y: window._lastMouseY || 0 })")
    src_x, src_y = current.get("x", 0.0), current.get("y", 0.0)

    n_points = random.randint(35, 55)
    points = _bezier_points(src_x, src_y, dest_x, dest_y, n=n_points, overshoot=overshoot)

    step_delay = speed_ms / n_points / 1000.0

    for px, py in points:
        await page.mouse.move(px, py)
        await asyncio.sleep(max(0, random.gauss(step_delay, step_delay * 0.25)))

    await page.evaluate(
        "([x, y]) => { window._lastMouseX = x; window._lastMouseY = y; }",
        [dest_x, dest_y],
    )


async def human_type(
    page: Page,
    selector: str,
    text: str,
    *,
    wpm: float = 45.0,
    typo_rate: float = 0.02,
    pause_after_at: bool = True,
    cognitive_pause_chance: float = 0.05,
) -> None:
    """
    Type text into a field with realistic keystroke dynamics.

    Keystroke timing model:
      - Inter-key delay drawn from log-normal (dwell + flight time combined)
      - wpm controls the mean; σ = 30% of mean
      - typo_rate: probability of hitting adjacent key → backspace → correct key
      - pause_after_at: humans hesitate after typing '@' (recalling domain)
      - cognitive_pause_chance: random "thinking" pause (300–800 ms)
    """
    el = await page.query_selector(selector)
    if el is None:
        return

    # Move to the field first
    await human_move_to(page, el, overshoot=False, speed="normal")
    await el.click()
    await asyncio.sleep(random.uniform(0.08, 0.18))

    # ms per character at given WPM (5 chars/word average)
    ms_per_char = 60_000.0 / (wpm * 5.0)

    for char in text:
        # Cognitive pause — occasional "thinking" moment
        if random.random() < cognitive_pause_chance:
            await asyncio.sleep(random.uniform(0.3, 0.8))

        # Typo simulation
        if char.lower() in _ADJACENT and random.random() < typo_rate:
            typo_char = random.choice(_ADJACENT[char.lower()])
            if char.isupper():
                typo_char = typo_char.upper()
            await page.keyboard.type(typo_char)
            await asyncio.sleep(random.gauss(ms_per_char, ms_per_char * 0.3) / 1000)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.gauss(80, 20) / 1000)

        await page.keyboard.type(char)
        delay = random.gauss(ms_per_char, ms_per_char * 0.3) / 1000
        await asyncio.sleep(max(0.03, delay))

        # Pause after '@' — users mentally switch from username to domain
        if char == "@" and pause_after_at:
            await asyncio.sleep(random.uniform(0.25, 0.65))


async def human_scroll(
    page: Page,
    direction: Literal["down", "up"] = "down",
    distance_px: int = 400,
) -> None:
    """
    Scroll with eased velocity curve and micro-pauses.
    Real users do not scroll at constant velocity.
    """
    sign = 1 if direction == "down" else -1
    steps = random.randint(6, 12)
    remaining = abs(distance_px)

    for i in range(steps):
        # Ease-in-out: accelerate then decelerate
        t = i / (steps - 1) if steps > 1 else 1.0
        ease = math.sin(t * math.pi)
        chunk = int((remaining / steps) * (0.5 + ease * 0.5))
        chunk = max(20, min(chunk, remaining))

        await page.mouse.wheel(0, sign * chunk)
        remaining -= chunk
        await asyncio.sleep(random.gauss(0.08, 0.025))

        # Occasional mid-scroll pause (reading behavior)
        if random.random() < 0.12:
            await asyncio.sleep(random.uniform(0.2, 0.6))

    if remaining > 0:
        await page.mouse.wheel(0, sign * remaining)
