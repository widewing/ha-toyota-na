
import json
import logging
import aiohttp
from urllib.parse import urlparse, parse_qs, urlencode

from toyota_na import ToyotaOneAuth
from toyota_na.exceptions import LoginError


async def authorize(self, username, password, otp=None):
    async with aiohttp.ClientSession() as session:
        headers = {"Accept-API-Version": "resource=2.1, protocol=1.0"}

        data = {}
        otp_brake = False
        if otp is not None:    # Retrieve callbacks if we have the otp code
            data = self.otp_callbacks
            
        for _ in range(10):
            if "callbacks" in data:
                for cb in data["callbacks"]:
                    logging.debug(cb["type"] + ": " + cb["output"][0]["value"])
                    if cb["type"] == "NameCallback" and cb["output"][0]["value"] == "User Name":
                        cb["input"][0]["value"] = username
                    elif cb["type"] == "NameCallback" and cb["output"][0]["value"] == "ui_locales":
                        cb["input"][0]["value"] = "en-US"
                    elif cb["type"] == "PasswordCallback" and cb["output"][0]["value"] == "Password":
                        cb["input"][0]["value"] = password
                    elif cb["type"] == "PasswordCallback" and cb["output"][0]["value"] == "One Time Password":
                        if otp is None:
                            otp_brake = True
                            break
                        cb["input"][0]["value"] = otp
                    elif cb["type"] == "TextOutputCallback" and cb["output"][0]["value"] == "Invalid OTP":
                        logging.error("Invalid OTP")
                        raise LoginError()
            
            if otp_brake:
                self.otp_callbacks = data # Store callback to restart auth loop when we have the otp
                logging.debug("Fetching otp...")
                return data
        
            async with session.post(f"{ToyotaOneAuth.AUTHENTICATE_URL}", json=data, headers=headers) as resp:
                if resp.status != 200:
                    logging.info(await resp.text())
                    raise LoginError()
                data = await resp.json()
                if "tokenId" in data:
                    break
        if "tokenId" not in data:
            logging.error(json.dumps(data))
            raise LoginError()
        headers["Cookie"] = f"iPlanetDirectoryPro={data['tokenId']}"
        auth_params = {
            "client_id": "oneappsdkclient",
            "scope": "openid profile write",
            "response_type": "code",
            "redirect_uri": "com.toyota.oneapp:/oauth2Callback",
            "code_challenge": "plain",
            "code_challenge_method": "plain"
        }
        AUTHORIZE_URL_QS = f"{ToyotaOneAuth.AUTHORIZE_URL}?{urlencode(auth_params)}"
        async with session.get(AUTHORIZE_URL_QS, headers=headers, allow_redirects=False) as resp:
            if resp.status != 302:
                logging.error(resp.text())
                raise LoginError()
            redir = resp.headers["Location"]
            query = parse_qs(urlparse(redir).query)
            if "code" not in query:
                logging.error(redir)
                raise LoginError()
            return query["code"][0]
            
async def login(self, username, password, otp):
    authorization_code = await self.authorize(username, password, otp)
    await self.request_tokens(authorization_code)