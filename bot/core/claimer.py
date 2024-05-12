import asyncio
from time import time
from datetime import datetime
from urllib.parse import unquote

import aiohttp
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.types import User
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered
from pyrogram.raw.functions.messages import RequestWebView
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import settings
from bot.utils import logger
from bot.exceptions import InvalidSession
from db.functions import get_user_proxy, get_user_agent, save_log
from .headers import headers


local_db = {}


class Claimer:
    def __init__(self, tg_client: Client, db_pool: async_sessionmaker, user_data: User):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.db_pool = db_pool
        self.user_data = user_data

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            if not self.tg_client.is_connected:
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            web_view = await self.tg_client.invoke(RequestWebView(
                peer=await self.tg_client.resolve_peer('pocketfi_bot'),
                bot=await self.tg_client.resolve_peer('pocketfi_bot'),
                platform='android',
                from_bot_menu=False,
                url='https://botui.pocketfi.org/mining/'
            ))

            auth_url = web_view.url
            tg_web_data = unquote(
                string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0])

            if self.tg_client.is_connected:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    async def get_mining_data(self, http_client: aiohttp.ClientSession) -> dict[str]:
        try:
            response = await http_client.get('https://bot.pocketfi.org/mining/getUserMining')
            response.raise_for_status()

            response_json = await response.json()
            mining_data = response_json['userMining']

            return mining_data
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when getting Profile Data: {error}")
            await asyncio.sleep(delay=3)

    async def send_claim(self, http_client: aiohttp.ClientSession) -> bool:
        try:
            response = await http_client.post('https://bot.pocketfi.org/mining/claimMining', json={})
            response.raise_for_status()

            return True
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when Claiming: {error}")
            await asyncio.sleep(delay=3)

            return False

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")

    async def run(self, proxy: str | None) -> None:
        access_token_created_time = 0
        claim_time = 0

        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        user_agent = await get_user_agent(db_pool=self.db_pool, phone_number=self.user_data.phone_number)
        headers['User-Agent'] = user_agent

        async with aiohttp.ClientSession(headers=headers, connector=proxy_conn) as http_client:
            if proxy:
                await self.check_proxy(http_client=http_client, proxy=proxy)

            try:
                local_token = local_db[self.session_name]['Token']
                if not local_token:
                    tg_web_data = await self.get_tg_web_data(proxy=proxy)

                    http_client.headers["telegramRawData"] = tg_web_data

                    local_db[self.session_name]['Token'] = tg_web_data

                    mining_data = await self.get_mining_data(http_client=http_client)

                    last_claim_time = datetime.fromtimestamp(
                        int(str(mining_data['dttmLastClaim'])[:-3])).strftime('%Y-%m-%d %H:%M:%S')
                    claim_deadline_time = datetime.fromtimestamp(
                        int(str(mining_data['dttmClaimDeadline'])[:-3])).strftime('%Y-%m-%d %H:%M:%S')

                    logger.info(f"{self.session_name} | Last claim time: {last_claim_time}")
                    logger.info(f"{self.session_name} | Claim deadline time: {claim_deadline_time}")
                else:
                    http_client.headers["telegramRawData"] = local_token
                    claim_time = local_db[self.session_name]['ClaimTime']

                mining_data = await self.get_mining_data(http_client=http_client)

                balance = mining_data['gotAmount']
                available = mining_data['miningAmount']
                speed = mining_data['speed']

                logger.info(f"{self.session_name} | Balance: <c>{balance}</c> | "
                            f"Available: <e>{available}</e> | "
                            f"Speed: <m>{speed}</m>")

                if time() - claim_time >= settings.SLEEP_BETWEEN_CLAIM * 60 and available > 0:
                    retry = 0
                    while retry <= settings.CLAIM_RETRY:
                        status = await self.send_claim(http_client=http_client)
                        if status:
                            mining_data = await self.get_mining_data(http_client=http_client)

                            balance = mining_data['gotAmount']

                            logger.success(f"{self.session_name} | Successful claim | "
                                           f"Balance: <c>{balance}</c> (<g>+{available}</g>)")
                            logger.info(f"Next claim in {settings.SLEEP_BETWEEN_CLAIM}min")

                            await save_log(
                                db_pool=self.db_pool,
                                phone=self.user_data.phone_number,
                                status="CLAIM",
                                amount=balance,
                            )

                            claim_time = time()

                            local_db[self.session_name]['ClaimTime'] = claim_time

                            return

                        await save_log(
                            db_pool=self.db_pool,
                            phone=self.user_data.phone_number,
                            status="ERROR",
                            amount=balance,
                        )

                        logger.info(f"{self.session_name} | Retry <y>{retry}</y> of <e>{settings.CLAIM_RETRY}</e>")
                        retry += 1

            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=3)


async def run_claimer(tg_client: Client, db_pool: async_sessionmaker):
    try:
        async with tg_client:
            user_data = await tg_client.get_me()

        if not local_db.get(tg_client.name):
            local_db[tg_client.name] = {'Token': '', 'ClaimTime': 0}

        proxy = None
        if settings.USE_PROXY_FROM_DB:
            proxy = await get_user_proxy(db_pool=db_pool, phone_number=user_data.phone_number)

        await Claimer(tg_client=tg_client, db_pool=db_pool, user_data=user_data).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
