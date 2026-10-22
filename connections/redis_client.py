"""Redis Cluster client for cache invalidation (DUMP_SUBS_CACHE keys)."""
from redis.cluster import RedisCluster, ClusterNode

from core.config import AppConfig
from connections.base import BaseConnection


class RedisCacheClient(BaseConnection):
    """Lazy, reusable RedisCluster client.

    Cluster-mode only (redis-py >= 4.1); decode_responses=True; the client
    handles slot routing, callers just use unlink(key).
    """

    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config

    def get_client(self) -> RedisCluster:
        if self._conn is not None:
            return self._conn
        nodes = [ClusterNode(host, int(port))
                 for host, port in self._config.redis.get("nodes", [])]
        self._conn = RedisCluster(
            startup_nodes=nodes,
            password=self._config.redis.get("password") or None,
            decode_responses=True,
            socket_timeout=5
        )
        return self._conn

    def invalidate(self, key: str):
        """Best-effort UNLINK of a cache key.

        Returns (True, message) on success, (False, error_message) on failure.
        The success message embeds the raw UNLINK integer reply (number of
        keys actually removed): 1 = an existing cache entry was deleted,
        0 = the key was already absent. Never raises - cache failure must
        not fail the DB update.
        """
        try:
            reply = self.get_client().unlink(key)
            if reply:
                msg = f"{key} (redis UNLINK replied {reply}: cache entry deleted)"
            else:
                msg = (f"{key} (redis UNLINK replied 0: "
                       f"key was already absent, nothing to delete)")
            return True, msg
        except Exception as e:
            self._conn = None  # force a fresh connection next time
            return False, str(e)

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
