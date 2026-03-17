"""Google Meet bot — joins via Playwright headless Chromium."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright, Browser, Page
from loguru import logger

from config import settings
from models import Meeting
from .base_bot import BaseMeetingBot


class GoogleMeetBot(BaseMeetingBot):
    """Automates joining a Google Meet session and detecting when it ends."""

    def __init__(self, meeting: Meeting, audio_output_path: Path):
        super().__init__(meeting, audio_output_path)
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def join(self) -> None:
        logger.info(f"[GoogleMeet] Joining: {self.meeting.join_url}")
        self._playwright = await async_playwright().start()

        # Launch with virtual audio args so PulseAudio capture works
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        context = await self._browser.new_context(
            permissions=["camera", "microphone"],
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        self._page = await context.new_page()

        # Sign in to Google if credentials provided
        if settings.bot_google_email and settings.bot_google_password:
            await self._google_sign_in()

        await self._page.goto(self.meeting.join_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Dismiss camera/mic prompts
        await self._dismiss_av_prompts()

        # Click "Join now" / "Ask to join" button
        await self._click_join_button()

        self._joined = True
        logger.info("[GoogleMeet] Joined successfully")

    async def _google_sign_in(self) -> None:
        """Sign in to Google account."""
        page = self._page
        await page.goto("https://accounts.google.com/signin", wait_until="networkidle")
        await page.fill('input[type="email"]', settings.bot_google_email)
        await page.click("#identifierNext")
        await asyncio.sleep(2)
        await page.fill('input[type="password"]', settings.bot_google_password)
        await page.click("#passwordNext")
        await asyncio.sleep(3)

    async def _dismiss_av_prompts(self) -> None:
        """Turn off mic and camera before joining to avoid echo/spam."""
        page = self._page
        for selector in [
            '[data-is-muted="false"][data-tooltip*="microphone"]',
            'button[aria-label*="microphone"]',
            '[aria-label*="Turn off microphone"]',
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    break
            except Exception:
                pass

    async def _click_join_button(self) -> None:
        page = self._page
        join_selectors = [
            'button:has-text("Join now")',
            'button:has-text("Ask to join")',
            'button:has-text("Join")',
            '[data-idom-class*="join"]',
        ]
        for selector in join_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=5000):
                    await btn.click()
                    logger.info(f"[GoogleMeet] Clicked join button: {selector}")
                    await asyncio.sleep(3)
                    return
            except Exception:
                pass
        logger.warning("[GoogleMeet] Could not find join button — proceeding anyway")

    async def is_meeting_active(self) -> bool:
        """Return False when the 'Return to home screen' or similar end indicator appears."""
        if not self._page:
            return False
        try:
            end_indicators = [
                'text="You\'ve left the meeting"',
                'text="The meeting has ended"',
                'text="Return to home screen"',
            ]
            for selector in end_indicators:
                el = self._page.locator(selector)
                if await el.is_visible(timeout=500):
                    return False
        except Exception:
            pass
        return True

    async def leave(self) -> None:
        logger.info("[GoogleMeet] Leaving meeting")
        if self._page:
            try:
                leave_btn = self._page.locator('[aria-label*="Leave call"], button:has-text("Leave call")').first
                if await leave_btn.is_visible(timeout=2000):
                    await leave_btn.click()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._joined = False
