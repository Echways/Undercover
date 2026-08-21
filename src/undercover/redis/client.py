from redis.asyncio import Redis

from undercover.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(str(settings.redis_url), decode_responses=True)


async def check_redis_connection(client: Redis) -> None:
    await client.ping()
