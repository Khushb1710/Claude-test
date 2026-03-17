"""Microsoft Teams bot — joins via the Teams web app using Playwright."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright, Browser, Page
from loguru import logger

from config import settings
from models import Meeting
from .base_bot import BaseMeetingBot


class TeamsBot(BaseMeetingBot):
    """Automates joining a Microsoft Teams meeting via the browser."""

    def __init__(self, meeting: Meeting, audio_output_path: Path):
        super().__init__(meeting, audio_output_path)
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def join(self) -> None:
        logger.info(f"[Teams] Joining: {self.meeting.join_url}")

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

        # Sign in if credentials provided
        if settings.bot_microsoft_email and settings.bot_microsoft_password:
            await self._microsoft_sign_in()

        await self._page.goto(self.meeting.join_url, wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # Handle "Use the web app instead" link
        await self._use_web_app()

        # Fill guest name if not signed in
        await self._enter_guest_name()

        # Dismiss mic/camera prompts and join
        await self._click_join()

        self._joined = True
        logger.info("[Teams] Joined successfully")

    async def _microsoft_sign_in(self) -> None:
        page = self._page
        await page.goto("https://login.microsoftonline.com/", wait_until="networkidle")
        await page.fill('input[type="email"]', settings.bot_microsoft_email)
        await page.click('input[type="submit"]')
        await asyncio.sleep(2)
        await page.fill('input[type="password"]', settings.bot_microsoft_password)
        await page.click('input[type="submit"]')
        await asyncio.sleep(3)
        # Handle "Stay signed in?" prompt
        try:
            await page.click('input[value="No"]', timeout=3000)
        except Exception:
            pass

    async def _use_web_app(self) -> None:
        """Click 'Use the web app instead' if Teams app prompt appears."""
        try:
            btn = self._page.locator('a:has-text("Use the web app instead"), button:has-text("Use the web app")').first
            if await btn.is_visible(timeout=4000):
                await btn.click()
                await asyncio.sleep(2)
        except Exception:
            pass

    async def _enter_guest_name(self) -> None:
        try:
            name_input = self._page.locator('input[placeholder*="name" i], input[id*="userName"]').first
            if await name_input.is_visible(timeout=3000):
                await name_input.fill("AI Note Taker")
        except Exception:
            pass

    async def _click_join(self) -> None:
        page = self._page
        # Mute mic/camera first
        for mute_sel in ['button[aria-label*="Microphone"]', 'button[id*="microphone"]']:
            try:
                btn = page.locator(mute_sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    break
            except Exception:
                pass

        join_selectors = [
            'button:has-text("Join now")',
            'button:has-text("Join")',
            '[data-tid="prejoin-join-button"]',
        ]
        for selector in join_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=5000):
                    await btn.click()
                    await asyncio.sleep(3)
                    logger.info(f"[Teams] Clicked: {selector}")
                    return
            except Exception:
                pass
        logger.warning("[Teams] Could not find join button")

    async def is_meeting_active(self) -> bool:
        if not self._page:
            return False
        try:
            end_indicators = [
                'text="The meeting has ended"',
                'text="You left the meeting"',
                '[data-tid="meeting-ended-banner"]',
            ]
            for sel in end_indicators:
                if await self._page.locator(sel).is_visible(timeout=500):
                    return False
        except Exception:
            pass
        return True

    async def leave(self) -> None:
        logger.info("[Teams] Leaving meeting")
        if self._page:
            try:
                leave_btn = self._page.locator(
                    'button[aria-label*="Leave"], button:has-text("Leave")'
                ).first
                if await leave_btn.is_visible(timeout=2000):
                    await leave_btn.click()
                    await asyncio.sleep(1)
                    confirm = self._page.locator('button:has-text("Leave meeting")').first
                    if await confirm.is_visible(timeout=2000):
                        await confirm.click()
            except Exception:
                pass
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._joined = False
