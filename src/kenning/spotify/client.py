"""Spotify Web API client -- playback control + search.

Thin wrapper over the REST API. Every call attaches a fresh access
token from :class:`~kenning.spotify.auth.SpotifyAuth` and goes through an
injectable ``request_fn`` (matches ``requests.request``) so unit tests
never hit the network. Methods return small result objects / plain
dicts; the voice layer turns those into spoken lines.

Playback-control endpoints (play/pause/next/volume/...) require Spotify
Premium and an ACTIVE device. When nothing is playing and no device is
active, Spotify returns 404 "NO_ACTIVE_DEVICE"; :meth:`ensure_device`
transfers playback to the user's last/most-available device first.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from kenning.spotify.auth import SpotifyAuth, SpotifyAuthError

logger = logging.getLogger("kenning.spotify.client")

__all__ = ["SpotifyClient", "SpotifyAPIError", "NowPlaying", "Device"]

API = "https://api.spotify.com/v1"

RequestFn = Callable[..., Any]


class SpotifyAPIError(RuntimeError):
    """A Web API call returned a non-success status."""


@dataclass(frozen=True)
class NowPlaying:
    """The currently-playing item (or a paused/empty state)."""

    is_playing: bool
    track: str = ""
    artist: str = ""
    device: str = ""

    def spoken(self) -> str:
        if not self.track:
            return "Nothing is playing right now."
        verb = "Playing" if self.is_playing else "Paused on"
        who = f" by {self.artist}" if self.artist else ""
        return f"{verb} {self.track}{who}."


@dataclass(frozen=True)
class Device:
    """A Spotify Connect playback device."""

    id: str
    name: str
    is_active: bool
    type: str = ""


def _default_request() -> RequestFn:
    import requests

    return requests.request


class SpotifyClient:
    """Spotify Web API client bound to one authorized user."""

    def __init__(
        self,
        auth: SpotifyAuth,
        *,
        request_fn: Optional[RequestFn] = None,
        default_device: str = "",
    ) -> None:
        """Args:
        auth: the token provider.
        request_fn: injectable HTTP (defaults to ``requests.request``).
        default_device: preferred device NAME to fall back to when no
            device is active (empty = first available).
        """
        self._auth = auth
        self._request = request_fn or _default_request()
        self._default_device = default_device

    # -- low-level -----------------------------------------------------

    def _call(
        self, method: str, path: str, *,
        params: Optional[dict] = None, json_body: Optional[dict] = None,
        allow_404: bool = False, _retried: bool = False,
    ) -> Any:
        token = self._auth.access_token()
        resp = self._request(
            method, API + path,
            headers={"Authorization": f"Bearer {token}"},
            params=params, json=json_body, timeout=15,
        )
        code = getattr(resp, "status_code", 500)
        if code == 204 or code == 202:
            return None
        if allow_404 and code == 404:
            return None
        if code == 401:
            # An EXPIRED / revoked token is a real auth problem -> re-authorize.
            raise SpotifyAPIError(
                "Spotify session expired -- re-authorize "
                "(run scripts/spotify_setup.py). (401)"
            )
        if code == 403:
            # A 403 with a VALID token is almost never an auth problem -- it is
            # usually "no ACTIVE device" or a transient device-state restriction
            # (Spotify rejects a playback write when the target device just
            # connected or nothing is queued). Activate a device and retry ONCE,
            # then surface a DEVICE-oriented message, not "re-authorize".
            if (not _retried and method in ("PUT", "POST")
                    and path.startswith("/me/player")):
                try:
                    if self.ensure_device():
                        return self._call(
                            method, path, params=params, json_body=json_body,
                            allow_404=allow_404, _retried=True)
                except SpotifyAPIError:
                    pass
            raise SpotifyAPIError(
                "Spotify won't take that right now -- make sure Spotify is open "
                "and playing on a device, then try again. (403)"
            )
        if code >= 400:
            raise SpotifyAPIError(f"Spotify API {method} {path} -> {code}")
        try:
            return resp.json()
        except Exception:  # noqa: BLE001 - empty body on a 200/PUT
            return None

    # -- state ---------------------------------------------------------

    def now_playing(self) -> NowPlaying:
        """What's playing right now (or an empty state)."""
        data = self._call("GET", "/me/player", allow_404=True)
        if not data or not data.get("item"):
            return NowPlaying(is_playing=False)
        item = data["item"]
        artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
        return NowPlaying(
            is_playing=bool(data.get("is_playing")),
            track=item.get("name", ""),
            artist=artists,
            device=(data.get("device") or {}).get("name", ""),
        )

    def devices(self) -> list[Device]:
        data = self._call("GET", "/me/player/devices") or {}
        out: list[Device] = []
        for d in data.get("devices", []):
            out.append(Device(
                id=d.get("id", ""), name=d.get("name", ""),
                is_active=bool(d.get("is_active")), type=d.get("type", ""),
            ))
        return out

    def ensure_device(self) -> Optional[str]:
        """Make sure SOME device is active; transfer to one if not.

        Returns the active device id, or None when the user has no
        Spotify Connect device available at all (nothing open)."""
        devs = self.devices()
        if not devs:
            return None
        active = next((d for d in devs if d.is_active), None)
        if active:
            return active.id
        pick = None
        if self._default_device:
            pick = next(
                (d for d in devs
                 if d.name.lower() == self._default_device.lower()), None,
            )
        pick = pick or devs[0]
        # _retried=True so a 403 on the transfer itself can't recurse back into
        # the ensure_device retry in _call.
        self._call("PUT", "/me/player",
                   json_body={"device_ids": [pick.id], "play": False},
                   _retried=True)
        return pick.id

    # -- transport -----------------------------------------------------

    def resume(self) -> None:
        self.ensure_device()
        self._call("PUT", "/me/player/play")

    def pause(self) -> None:
        self._call("PUT", "/me/player/pause", allow_404=True)

    def next_track(self) -> None:
        self.ensure_device()
        self._call("POST", "/me/player/next")

    def previous_track(self) -> None:
        self.ensure_device()
        self._call("POST", "/me/player/previous")

    def set_volume(self, percent: int) -> None:
        percent = max(0, min(100, int(percent)))
        self._call("PUT", "/me/player/volume",
                   params={"volume_percent": percent}, allow_404=True)

    def current_volume(self) -> Optional[int]:
        data = self._call("GET", "/me/player", allow_404=True)
        if not data:
            return None
        return (data.get("device") or {}).get("volume_percent")

    def set_shuffle(self, state: bool) -> None:
        self._call("PUT", "/me/player/shuffle",
                   params={"state": str(bool(state)).lower()}, allow_404=True)

    def set_repeat(self, mode: str) -> None:
        if mode not in ("track", "context", "off"):
            mode = "off"
        self._call("PUT", "/me/player/repeat",
                   params={"state": mode}, allow_404=True)

    # -- search + play -------------------------------------------------

    def search_first(self, query: str, kind: str) -> Optional[dict]:
        """First search hit of ``kind`` (track/artist/album/playlist)."""
        data = self._call("GET", "/search", params={
            "q": query, "type": kind, "limit": 5,
        }) or {}
        items = (data.get(kind + "s") or {}).get("items") or []
        items = [i for i in items if i]
        return items[0] if items else None

    def play_query(self, query: str, kind: str = "track") -> str:
        """Search for ``query`` and start playing the first match.

        ``kind`` = track plays that one song; artist/album/playlist
        plays the whole context. Returns a spoken confirmation, or a
        clear "couldn't find it" message.
        """
        hit = self.search_first(query, kind)
        if hit is None:
            return f"I couldn't find {query} on Spotify."
        self.ensure_device()
        name = hit.get("name", query)
        if kind == "track":
            artists = ", ".join(
                a.get("name", "") for a in hit.get("artists", []))
            self._call("PUT", "/me/player/play",
                       json_body={"uris": [hit["uri"]]})
            who = f" by {artists}" if artists else ""
            return f"Playing {name}{who}."
        # artist / album / playlist -> play the whole context.
        self._call("PUT", "/me/player/play",
                   json_body={"context_uri": hit["uri"]})
        label = {"artist": "", "album": "the album ",
                 "playlist": "the playlist "}.get(kind, "")
        return f"Playing {label}{name}."

    def queue_query(self, query: str) -> str:
        """Add the first matching track to the up-next queue."""
        hit = self.search_first(query, "track")
        if hit is None:
            return f"I couldn't find {query} to queue."
        self.ensure_device()
        self._call("POST", "/me/player/queue", params={"uri": hit["uri"]})
        artists = ", ".join(a.get("name", "") for a in hit.get("artists", []))
        who = f" by {artists}" if artists else ""
        return f"Queued {hit.get('name', query)}{who}."

    # -- structured search+queue (Twitch !song / !album requests) -------
    #
    # The chat-request path needs STRUCTURED results (exact name/artists for
    # the chat confirmation, the overlay card, and the spoken line are three
    # different renderings), so these return dicts instead of spoken strings.
    # The voice path above (queue_query, spoken-string contract) is untouched.

    def _search_smart(self, query: str, kind: str) -> Optional[dict]:
        """Search ``kind`` by free text, with a precision pass for "X by Y".

        Viewers type every variant: "Dance Dance by cage the elephant",
        "Dance Dance cage the elephant", bare "Dance Dance". When the text
        contains " by ", try a FIELD-FILTERED query first (name filter +
        artist filter, split on the LAST " by " since the artist tail comes
        last) -- then always fall back to the raw text so titles that
        legitimately contain "by" ("Stand By Me") still match."""
        q = (query or "").strip()
        if not q:
            return None
        lowered = q.lower()
        if " by " in lowered:
            cut = lowered.rfind(" by ")
            name, artist = q[:cut].strip(), q[cut + 4:].strip()
            if name and artist:
                field = "track" if kind == "track" else "album"
                hit = self.search_first(
                    f'{field}:"{name}" artist:"{artist}"', kind)
                if hit is not None:
                    return hit
        return self.search_first(q, kind)

    def _queue_uri(self, uri: str) -> None:
        self._call("POST", "/me/player/queue", params={"uri": uri})

    def search_and_queue_track(self, query: str) -> Optional[dict]:
        """Search ``query`` and queue the best matching TRACK.

        Returns ``{"kind": "track", "name", "artists", "album"}`` on success,
        None when nothing matched. API/device errors raise
        :class:`SpotifyAPIError` (the caller refunds on those)."""
        hit = self._search_smart(query, "track")
        if hit is None or not hit.get("uri"):
            return None
        self.ensure_device()
        self._queue_uri(hit["uri"])
        return {
            "kind": "track",
            "name": hit.get("name", query),
            "artists": ", ".join(
                a.get("name", "") for a in hit.get("artists", []) if a),
            "album": (hit.get("album") or {}).get("name", ""),
        }

    def search_and_queue_album(
        self, query: str, *, max_tracks: int = 30,
    ) -> Optional[dict]:
        """Search ``query`` for an ALBUM and queue its tracks in order.

        Spotify's queue endpoint takes ONE uri per call, so the album is
        queued track-by-track (capped at ``max_tracks`` to bound the HTTP
        fan-out; a standard album fits comfortably). Returns
        ``{"kind": "album", "name", "artists", "track_count"}`` on success,
        None when no album matched or it had no tracks. API/device errors
        raise :class:`SpotifyAPIError` mid-way; the caller treats the whole
        request as failed (partial queueing is harmless -- extra songs, no
        replay risk)."""
        hit = self._search_smart(query, "album")
        if hit is None or not hit.get("id"):
            return None
        album_id = hit["id"]
        uris: list[str] = []
        params: Optional[dict] = {"limit": 50}
        path = f"/albums/{album_id}/tracks"
        while path and len(uris) < max_tracks:
            data = self._call("GET", path, params=params) or {}
            for t in data.get("items") or []:
                if t and t.get("uri"):
                    uris.append(t["uri"])
                    if len(uris) >= max_tracks:
                        break
            nxt = data.get("next")
            if nxt and len(uris) < max_tracks:
                # 'next' is a full URL; keep only the path+query via the API
                # base split so _call re-attaches auth cleanly.
                path = nxt.split(API, 1)[-1] if API in nxt else None
                params = None
            else:
                path = None
        if not uris:
            return None
        self.ensure_device()
        for uri in uris:
            self._queue_uri(uri)
        return {
            "kind": "album",
            "name": hit.get("name", query),
            "artists": ", ".join(
                a.get("name", "") for a in hit.get("artists", []) if a),
            "track_count": len(uris),
        }

    # -- seek + library ------------------------------------------------

    def seek(self, position_ms: int = 0) -> None:
        """Seek within the current track (0 = restart from the beginning)."""
        self.ensure_device()
        self._call("PUT", "/me/player/seek",
                   params={"position_ms": max(0, int(position_ms))},
                   allow_404=True)

    def _current_item(self) -> Optional[dict]:
        """Raw currently-playing item (carries id + name + artists), or None."""
        data = self._call("GET", "/me/player", allow_404=True)
        if not data or not data.get("item"):
            return None
        return data["item"]

    def save_current_track(self) -> str:
        """Add the currently-playing track to the user's Liked Songs.

        Needs the ``user-library-modify`` scope (in DEFAULT_SCOPES)."""
        item = self._current_item()
        if not item or not item.get("id"):
            return "Nothing is playing to save."
        self._call("PUT", "/me/tracks", json_body={"ids": [item["id"]]})
        return f"Saved {item.get('name', 'this track')} to your library."

    def unsave_current_track(self) -> str:
        """Remove the currently-playing track from the user's Liked Songs."""
        item = self._current_item()
        if not item or not item.get("id"):
            return "Nothing is playing to remove."
        self._call("DELETE", "/me/tracks", json_body={"ids": [item["id"]]})
        return f"Removed {item.get('name', 'this track')} from your library."
