#!/usr/bin/env python
import asyncio
import json
import re

import requests
from base64 import urlsafe_b64encode
from hashlib import sha256
from secrets import token_urlsafe
from config import use_selenium

if use_selenium:
    from urllib.parse import urlencode
    from selenium import webdriver
    from selenium.webdriver import ActionChains
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
    from webdriver_manager.chrome import ChromeDriverManager

# To get first refresh token use script from this link:
# https://gist.github.com/ZipFile/c9ebedb224406f4f11845ab700124362

# Latest app version can be found using GET /v1/application-info/android
USER_AGENT = "PixivIOSApp/7.13.3 (iOS 14.6; iPhone13,2)"
REDIRECT_URI = "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback"
LOGIN_URL = "https://app-api.pixiv.net/web/v1/login"
AUTH_TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"
CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
REQUESTS_KWARGS = {
    # 'proxies': {
    #     'https': 'http://127.0.0.1:1087',
    # },
    # 'verify': False
}


def refresh_token(refresh_token):
    response = requests.post(
        AUTH_TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "include_policy": "true",
            "refresh_token": refresh_token,
        },
        headers={"User-Agent": USER_AGENT},
    )
    data = response.json()
    ttl = 0
    try:
        refresh_token = data["refresh_token"]
        ttl = data.get("expires_in", 0)
    except KeyError:
        print("unable to get pixiv refresh token!")
    return refresh_token, ttl


def s256(data):
    """S256 transformation method."""
    return urlsafe_b64encode(sha256(data).digest()).rstrip(b"=").decode("ascii")


def oauth_pkce(transform):
    """Proof Key for Code Exchange by OAuth Public Clients (RFC7636)."""
    code_verifier = token_urlsafe(32)
    code_challenge = transform(code_verifier.encode("ascii"))

    return code_verifier, code_challenge


async def selenium_login(log, pwd):
    caps = DesiredCapabilities.CHROME.copy()
    caps["goog:loggingPrefs"] = {"performance": "ALL"}  # enable performance logs

    driver = webdriver.Chrome(ChromeDriverManager().install(), desired_capabilities=caps)
    code_verifier, code_challenge = oauth_pkce(s256)
    login_params = {
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "client": "pixiv-android",
    }

    driver.get(f"{LOGIN_URL}?{urlencode(login_params)}")
    log_field = driver.find_element(By.CSS_SELECTOR,
                                  '#LoginComponent > form > div.input-field-group > div:nth-child(1)')
    pass_field = driver.find_element(By.CSS_SELECTOR,
                                  '#LoginComponent > form > div.input-field-group > div:nth-child(2)')
    button = driver.find_element(By.CSS_SELECTOR, '#LoginComponent > form > button')
    ActionChains(driver).\
        send_keys_to_element(log_field, log).\
        send_keys_to_element(pass_field, pwd).\
        move_to_element(button).click().perform()
    #

    ok = False
    for i in range(5):
        # wait for login
        if driver.current_url[:40] == "https://accounts.pixiv.net/post-redirect":
            ok = True
            break
        await asyncio.sleep(1)

    if not ok:
        return None

    # filter code url from performance logs
    code = None
    for row in driver.get_log('performance'):
        data = json.loads(row.get("message", {}))
        message = data.get("message", {})
        if message.get("method") == "Network.requestWillBeSent":
            url = message.get("params", {}).get("documentURL")
            if url[:8] == "pixiv://":
                code = re.search(r'code=([^&]*)', url).groups()[0]
                break

    driver.close()

    response = requests.post(
        AUTH_TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "include_policy": "true",
            "redirect_uri": REDIRECT_URI,
        },
        headers={
            "user-agent": USER_AGENT,
            "app-os-version": "14.6",
            "app-os": "ios",
        },
        **REQUESTS_KWARGS
    )

    data = response.json()
    return data["refresh_token"]
