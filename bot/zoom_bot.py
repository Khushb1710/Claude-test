"""Zoom bot — joins via the Zoom web client using Playwright."""

import asyncio
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright, Browser, Page
from loguru import logger

from config import settings
from models import Meeting
from .base_bot import BaseMeetingBot


class ZoomBot(BaseMeetingBot):
    """Automates joining a Zoom meeting via the browser web client."""

    def __init__(self, meeting: Meeting, audio_output_path: Path):
        super().__init__(meeting, audio_output_path)
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _to_web_client_url(join_url: str) -> str:
        """Convert a zoom.us/j/<id>?pwd=... URL to the web-client URL."""
        parsed = urlparse(join_url)
        meeting_id = parsed.path.strip("/").split("/")[-1]
        pwd = parse_qs(parsed.query).get("pwd", [""])[0]
        url = f"https://app.zoom.us/wc/{meeting_id}/join"
        if pwd:
            url += f"?pwd={pwd}"
        return url

    # ── Bot lifecycle ─────────────────────────────────────────────────────────

    async def join(self) -> None:
        web_url = self._to_web_client_url(self.meeting.join_url)
        logger.info(f"[Zoom] Joining via web client: {web_url}")

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await self._browser.new_context(
            permissions=["camera", "microphone"],
        )
        self._page = await context.new_page()
        await self._page.goto(web_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Enter name
        await self._enter_display_name()

        # Click "Join Audio" / "Join" button
        await self._click_join()

        self._joined = True
        logger.info("[Zoom] Joined successfully")

    async def _enter_display_name(self) -> None:
        page = self._page
        for selector in ['input[placeholder*="name" i]', 'input[id*="input-for-name"]']:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=3000):
                    await el.fill("AI Note Taker")
                    logger.debug("[Zoom] Filled display name")
                    return
            except Exception:
                pass

    async def _click_join(self) -> None:
        page = self._page
        join_selectors = [
            'button:has-text("Join")',
            'button:has-text("Join Audio")',
            '[class*="join-btn"]',
        ]
        for selector in join_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=5000):
                    await btn.click()
                    await asyncio.sleep(3)
                    logger.info(f"[Zoom] Clicked: {selector}")
                    return
            except Exception:
                pass
        logger.warning("[Zoom] Could not find join button")

    async def is_meeting_active(self) -> bool:
        if not self._page:
            return False
        try:
            end_indicators = [
                'text="This meeting has been ended"',
                'text="Meeting is over"',
                'text="The host has ended this meeting"',
            ]
            for sel in end_indicators:
                if await self._page.locator(sel).is_visible(timeout=500):
                    return False
        except Exception:
            pass
        return True

    async def leave(self) -> None:
        logger.info("[Zoom] Leaving meeting")
        if self._page:
            try:
                leave_btn = self._page.locator('button:has-text("Leave"), button:has-text("End")').first
                if await leave_btn.is_visible(timeout=2000):
                    await leave_btn.click()
                    await asyncio.sleep(1)
                    confirm = self._page.locator('button:has-text("Leave Meeting")').first
                    if await confirm.is_visible(timeout=2000):
                        await confirm.click()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._joined = False
