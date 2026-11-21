import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from urllib.parse import urlencode

# Isolate tests from the deployed bot database and Telegram credentials.
_TEST_DIR = tempfile.TemporaryDirectory()
os.environ["BOT_TOKEN"] = "123456:unit-test-token"
os.environ["DATABASE_PATH"] = os.path.join(_TEST_DIR.name, "test.sqlite3")

from aiohttp.test_utils import TestClient, TestServer
from xlinebot.db import connection
from xlinebot.miniapp_api import create_app, verify_init_data


class MiniAppAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = TestClient(TestServer(create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def _session_for(self, user_id):
        raw_token = f"game-test-token-{user_id}-" + ("z" * 40)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        with connection() as db:
            db.execute(
                "INSERT INTO miniapp_launch_tokens(token_hash,user_id,expires_at,used_at) VALUES(?,?,?,NULL)",
                (token_hash, user_id, int(time.time()) + 180),
            )
        response = await self.client.post(
            "/api/auth/exchange", json={"launch_token": raw_token}
        )
        self.assertEqual(response.status, 200)
        payload = await response.json()
        return {"X-XLINE-Session": payload["session_token"]}

    async def test_every_game_can_start(self):
        games = ("mines", "tower", "rocket", "slots", "blackjack")
        for offset, game in enumerate(games, start=1):
            user_id = 700000000 + offset
            headers = await self._session_for(user_id)
            response = await self.client.post(
                "/api/game/start",
                headers=headers,
                json={"game": game, "bet": 1, "mines": 5, "difficulty": "easy"},
            )
            self.assertEqual(response.status, 200, f"{game} failed to start")
            payload = await response.json()
            self.assertIn("balance", payload)
            self.assertEqual(payload.get("game", game), game)

    async def test_health_endpoint(self):
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        payload = await response.json()
        self.assertEqual(payload["status"], "ok")

    async def test_one_time_launch_token_exchange_and_session(self):
        raw_token = "test-launch-token-" + ("x" * 40)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = int(time.time())
        with connection() as db:
            db.execute(
                "INSERT INTO miniapp_launch_tokens(token_hash,user_id,expires_at,used_at) VALUES(?,?,?,NULL)",
                (token_hash, 123456789, now + 180),
            )

        response = await self.client.post(
            "/api/auth/exchange", json={"launch_token": raw_token}
        )
        self.assertEqual(response.status, 200)
        payload = await response.json()
        self.assertTrue(payload["session_token"])

        me = await self.client.get(
            "/api/me",
            headers={"X-XLINE-Session": payload["session_token"]},
        )
        self.assertEqual(me.status, 200)
        profile = await me.json()
        self.assertEqual(profile["id"], 123456789)
        self.assertEqual(profile["points"], 1000)

        replay = await self.client.post(
            "/api/auth/exchange", json={"launch_token": raw_token}
        )
        self.assertEqual(replay.status, 401)

    def test_telegram_init_data_signature(self):
        bot_token = os.environ["BOT_TOKEN"]
        pairs = {
            "auth_date": str(int(time.time())),
            "user": json.dumps({"id": 987654321, "first_name": "Test"}, separators=(",", ":")),
        }
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        pairs["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        signed = urlencode(pairs)
        self.assertEqual(verify_init_data(signed)["id"], 987654321)
        self.assertIsNone(verify_init_data(signed.replace("Test", "Attacker")))


if __name__ == "__main__":
    unittest.main()
