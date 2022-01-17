#!/usr/bin/env python
import requests

# To get first refresh token use script from this link:
# https://gist.github.com/ZipFile/c9ebedb224406f4f11845ab700124362
# Latest app version can be found using GET /v1/application-info/android
USER_AGENT = "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)"
AUTH_TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"
CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"


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
    try:
        refresh_token = data["refresh_token"]
        ttl = data.get("expires_in", 0)
    except KeyError:
        print("unable to get pixiv refresh token!")
    return refresh_token, ttl
