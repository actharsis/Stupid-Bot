import asyncio
import random
import typing
import json
import logging
import base64
import re
from queue import Queue

from playwright.async_api._context_manager import PlaywrightContextManager as AsyncPlaywrightInstance
from playwright.async_api._generated import Playwright
from playwright.async_api import Browser, Page, Response, Error
from playwright_stealth import stealth_async

log = logging.getLogger(__name__)


class RequestPatcher:
    def __init__(self, method, token, content_type, data = None):
        self.method = method
        self.token = token
        if data is not None:
            data = json.dumps(data)
        self.data = data
        self.content_type = content_type

    async def intercept_request(self, route, request):
        headers = {
            **request.headers,
            "authorization": f"Token {self.token}",
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br",
            "content-type": self.content_type,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
        }
        await route.continue_(headers=headers, method=self.method, post_data=self.data)


class CharacterAI:
    instance: AsyncPlaywrightInstance
    playwright: Playwright
    browser: Browser
    page: Page

    def __init__(self, token):
        self.request_queue = Queue()
        self.loading_state = True
        self.token = token
        self.user = None
        self.character = None

    async def start(self):
        self.instance = AsyncPlaywrightInstance()
        playwright = await self.instance.start()
        self.browser = await playwright.chromium.launch(
            headless=True,
            ignore_default_args=["--disable-extensions"],
            args=[
                "--no-default-browser-check", "--no-sandbox", "--disable-setuid-sandbox", "--no-first-run",
                "--disable-default-apps", "--disable-features=Translate", "--disable-infobars",
                "--mute-audio", "--ignore-certificate-errors", "--use-gl=egl",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
            ],
            timeout=1_200_000
        )
        self.page = await self.browser.new_page()
        await stealth_async(self.page)
        await self.open_cai_page()
        userdata = await self.get_user()
        self.user = userdata['user']['name']
        self.loading_state = False
        log.info('Character AI started')

    async def open_cai_page(self):
        response = await self.page.goto("https://beta.character.ai/search?")
        await self.try_to_leave_queue(response)

    async def try_to_leave_queue(self,
                                 response: typing.Optional[Response]):
        while True:
            content = await response.text()
            if "Waiting Room" not in content and "You are being rate limited" not in content:
                self.loading_state = False
                return
            self.loading_state = True
            pattern = r"Your estimated wait time is (\d+) min"
            match = re.search(pattern, content)
            if match:
                value = int(match.group(1))
                log.info(f'Cloudflare queue for {value} minute(s)')
            else:
                log.error("In queue forever? Tough")
            await asyncio.sleep(random.randint(20, 40))
            response = await self.page.reload()

    async def request_get(self, url: str, content_type: str = 'application/json'):
        if self.loading_state:
            log.info('cant do request GET in loading state')
            return
        page = await self.browser.new_page()
        await stealth_async(page)
        patcher = RequestPatcher('GET', self.token, content_type)
        await page.route("**/*", patcher.intercept_request)
        response = await page.goto(url)
        await self.try_to_leave_queue(response)
        content = await response.text()
        await page.close()
        return json.loads(content) if content else None

    async def request_post(self, url: str, data=None, content_type: str = 'application/json'):
        if self.loading_state:
            log.info('cant do request POST in loading state')
            return
        page = await self.browser.new_page()
        await stealth_async(page)
        patcher = RequestPatcher('POST', self.token, content_type, data)
        await page.route("**/*", patcher.intercept_request)
        response = await page.goto(url)
        await self.try_to_leave_queue(response)
        content = await response.text()
        await page.close()
        return json.loads(content) if content else None

    async def queue_wait(self):
        pass

    async def get_categories(self):
        url = 'https://beta.character.ai/chat/character/categories/'
        return await self.request_get(url)

    async def get_user_config(self):
        url = 'https://beta.character.ai/chat/config/'
        return await self.request_get(url)

    async def get_user(self):
        url = 'https://beta.character.ai/chat/user/'
        return await self.request_get(url)

    async def get_character_info(self, character_id):
        url = 'https://beta.character.ai/chat/character/info/'
        body = {'external_id': character_id}
        return await self.request_post(url, body)

    async def create_new_chat(self, character_id, load_char_data=True):
        body = {'character_external_id': character_id,
                'history_external_id': None}
        url = 'https://beta.character.ai/chat/history/create/'
        data = await self.request_post(url, body)
        character_data = (await self.get_character_info(character_id)).get('character') if load_char_data else None
        return AIChat(self, character_id, data, character_data)

    async def continue_chat(self, character_id, history_id, load_char_data=True):
        url = 'https://beta.character.ai/chat/history/continue/'
        body = {'character_external_id': character_id,
                'history_external_id': history_id}
        data = await self.request_post(url, body)
        character_data = (await self.get_character_info(character_id)).get('character') if load_char_data else None
        return AIChat(self, character_id, data, character_data)

    async def continue_last_or_create_chat(self, character_id, load_char_data=True):
        url = 'https://beta.character.ai/chat/history/continue/'
        body = {'character_external_id': character_id,
                'history_external_id': None}
        data = await self.request_post(url, body)
        if data is None:
            return await self.create_new_chat(character_id)
        character_data = (await self.get_character_info(character_id)).get('character') if load_char_data else None
        return AIChat(self, character_id, data, character_data)


async def data_stream_parse(download):
    data = b''
    async for chunk in download.follow_stream():
        chunk = base64.b64decode(chunk)
        data += chunk
    for res in data.split(b'\n'):
        if len(res) > 0:
            yield json.loads(res)


class AIChat:
    def __init__(self, client, character_id, continue_body, character_data=None):
        self.client = client
        self.character_id = character_id
        self.character_data = character_data
        self.external_id = continue_body.get('external_id')
        ai = next(filter(lambda participant: not participant['is_human'], continue_body['participants']))
        self.ai_id = ai['user']['username']

    async def send_message(self, message: str, content_type: str = 'application/json'):
        for attempt in range(3):
            if not self.client.loading_state:
                break
            await asyncio.sleep(5)
        if self.client.loading_state:
            log.error('cant do request POST (send message) in loading state')
            return
        data = {
            "history_external_id": self.external_id,
            "character_external_id": self.character_id,
            "text": message,
            "tgt": self.ai_id,
            "ranking_method": "random",
            "faux_chat": False,
            "staging": False,
            "model_server_address": None,
            "override_prefix": None,
            "override_rank": None,
            "rank_candidates": None,
            "filter_candidates": None,
            "prefix_limit": None,
            "prefix_token_limit": None,
            "livetune_coeff": None,
            "stream_params": None,
            "enable_tti": True,
            "initial_timeout": None,
            "insert_beginning": None,
            "translate_candidates": None,
            "stream_every_n_steps": 16,
            "chunks_to_pad": 8,
            "is_proactive": False
        }

        url = "https://beta.character.ai/chat/streaming/"
        page = await self.client.browser.new_page()
        await stealth_async(page)
        patcher = RequestPatcher('POST', self.client.token, content_type, data)
        await page.route("**/*", patcher.intercept_request)
        async with page.expect_download() as download_info:
            try:
                response = await page.goto(url)
                await self.client.try_to_leave_queue(response)
            except Error:
                pass
            download = await download_info.value
            async for answer in data_stream_parse(download):
                yield answer['replies'][0]['text'], \
                    answer['src_char']['participant']['name'], \
                    f"https://characterai.io/i/400/static/avatars/{answer['src_char']['avatar_file_name']}", \
                    answer['is_final_chunk']
        await page.close()
