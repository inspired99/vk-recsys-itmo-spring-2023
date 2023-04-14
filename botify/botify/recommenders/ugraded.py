from .recommender import Recommender
from .toppop import TopPop
import random
from collections import Counter


class Upgraded(Recommender):
    """
    Recommend tracks closest to the previous one.
    Fall back to the random recommender if no
    recommendations found for the track.
    """

    def __init__(self, tracks_redis, catalog, prev_buffer):
        self.tracks_redis = tracks_redis
        self.fallback = TopPop(tracks_redis.connection, catalog.top_tracks[:100])
        self.catalog = catalog
        self.user_buffer = prev_buffer
        self.user_buffer_limit = 10
        self.min_time = 0.25
        self.early_stop = 2
        self.max_duplicates = 2

    def add_track_to_buffer(self, user, track, track_time):
        """
        Check if buffer exceeds size or too much frequent, keep track of last self.user_buffer_limit tracks
        """
        self.user_buffer[user].append((track, track_time))

        counter = Counter(self.user_buffer[user])
        items_to_delete = []

        for k, v in counter.items():
            if v > self.max_duplicates:
                items_to_delete.append(k)

        self.user_buffer[user] = [i for i in self.user_buffer[user] if i not in items_to_delete]

        if len(self.user_buffer[user]) > self.user_buffer_limit:
            self.user_buffer[user].pop(0)

    def get_best_from_buffer(self, user):
        """
        Extract best track from recent
        """
        best = None

        if len(self.user_buffer[user]) > 0:
            sorted_by_time = sorted(self.user_buffer[user], reverse=True, key=lambda x: x[1])
            best = sorted_by_time[0][0]

        return best

    def check_early_stop(self, user):
        """
        Check if last k tracks were unlucky, so we need to change our pivot track
        """
        if not self.user_buffer[user]:
            return False

        last_tracks_time = list(filter(lambda x: x[1] < self.min_time, self.user_buffer[user]))
        return len(last_tracks_time) >= self.early_stop

    def recommend_next(self, user: int, prev_track: int, prev_track_time: float) -> int:
        self.add_track_to_buffer(user, prev_track, prev_track_time)

        if self.check_early_stop(user):
            best_recent_track = self.get_best_from_buffer(user)
            if best_recent_track is None:
                best_recent_track = prev_track
            previous_track = self.tracks_redis.get(best_recent_track)
            previous_track = self.catalog.from_bytes(previous_track)
        else:
            previous_track = self.tracks_redis.get(prev_track)
            previous_track = self.catalog.from_bytes(previous_track)

        if previous_track is None:
            return self.fallback.recommend_next(user, prev_track, prev_track_time)

        recommendations = previous_track.recommendations
        if not recommendations:
            return self.fallback.recommend_next(user, prev_track, prev_track_time)

        shuffled = list(recommendations)
        random.shuffle(shuffled)
        recommended = shuffled[0]
        return recommended
