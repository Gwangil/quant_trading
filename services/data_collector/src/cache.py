import redis
import pickle
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self, config):
        self.config = config
        self.redis_client = None
        self.connect()

    def connect(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.from_url(self.config.REDIS_URL)
            self.redis_client.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    def set(self, key, value, expire=None):
        """Set value in cache"""
        if not self.redis_client:
            return False

        try:
            if hasattr(value, 'to_dict'):
                value = value.to_dict('records')

            serialized = pickle.dumps(value)
            if expire:
                self.redis_client.setex(key, expire, serialized)
            else:
                self.redis_client.set(key, serialized)
            return True

        except Exception as e:
            logger.error(f"Cache set error for {key}: {e}")
            return False

    def get(self, key):
        """Get value from cache"""
        if not self.redis_client:
            return None

        try:
            value = self.redis_client.get(key)
            if value:
                return pickle.loads(value)
            return None

        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            return None

    def delete(self, key):
        """Delete key from cache"""
        if not self.redis_client:
            return False

        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error for {key}: {e}")
            return False

    def exists(self, key):
        """Check if key exists"""
        if not self.redis_client:
            return False

        try:
            return self.redis_client.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for {key}: {e}")
            return False

    def set_json(self, key, value, expire=None):
        """Set JSON value in cache"""
        if not self.redis_client:
            return False

        try:
            json_str = json.dumps(value)
            if expire:
                self.redis_client.setex(key, expire, json_str)
            else:
                self.redis_client.set(key, json_str)
            return True

        except Exception as e:
            logger.error(f"Cache set_json error for {key}: {e}")
            return False

    def get_json(self, key):
        """Get JSON value from cache"""
        if not self.redis_client:
            return None

        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None

        except Exception as e:
            logger.error(f"Cache get_json error for {key}: {e}")
            return None

    def set_with_ttl(self, key, value, ttl_seconds):
        """Set value with specific TTL"""
        return self.set(key, value, expire=ttl_seconds)

    def get_ttl(self, key):
        """Get remaining TTL for a key"""
        if not self.redis_client:
            return -1

        try:
            return self.redis_client.ttl(key)
        except Exception as e:
            logger.error(f"Cache get_ttl error for {key}: {e}")
            return -1

    def clear_pattern(self, pattern):
        """Clear all keys matching a pattern"""
        if not self.redis_client:
            return 0

        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache clear_pattern error for {pattern}: {e}")
            return 0