import os
import requests
import base64
import time
from dotenv import load_dotenv

load_dotenv()

# using itunes for search now, spotify kept giving 403

_token_cache = {
    "access_token": None,
    "expires_at": 0
}


def get_access_token():
    # not using spotify anymore but keeping this just in case
    global _token_cache

    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')

    if not client_id or not client_secret:
        return None

    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        res = requests.post("https://accounts.spotify.com/api/token", headers=headers, data={"grant_type": "client_credentials"})
        if res.status_code != 200:
            return None
        res_json = res.json()
        if "access_token" in res_json:
            _token_cache["access_token"] = res_json["access_token"]
            _token_cache["expires_at"] = time.time() + res_json.get("expires_in", 3600) - 60
            return res_json["access_token"]
        return None
    except:
        return None


def search_songs(query, limit=10):
    print(f"searching: {query}")
    return search_itunes(query, limit)


def search_itunes(query, limit=10):
    try:
        params = {
            "term": query,
            "media": "music",
            "entity": "song",
            "limit": limit
        }
        res = requests.get("https://itunes.apple.com/search", params=params)
        print(f"itunes status: {res.status_code}")

        if res.status_code != 200:
            print(f"itunes failed: {res.text[:200]}")
            return {"results": [], "total": 0}

        data = res.json()
        print(f"itunes found {data.get('resultCount', 0)} results")

        tracks = []
        for track in data.get('results', []):
            # itunes gives 100x100 thumbnails, we want bigger ones
            artwork = track.get('artworkUrl100', '')
            if artwork:
                artwork = artwork.replace('100x100', '600x600')

            tracks.append({
                "name": track.get('trackName', 'Unknown'),
                "artist": track.get('artistName', 'Unknown'),
                "album": track.get('collectionName', 'Unknown'),
                "album_art": artwork,
                "preview_url": track.get('previewUrl'),
                "spotify_url": track.get('trackViewUrl'),
                "duration_ms": track.get('trackTimeMillis', 0),
                "popularity": 0
            })

        return {"results": tracks, "total": len(tracks)}

    except Exception as e:
        print(f"itunes search error: {e}")
        return {"results": [], "total": 0}


def get_album_art(song_name, artist):
    try:
        params = {
            "term": f"{song_name} {artist}",
            "media": "music",
            "entity": "song",
            "limit": 1
        }
        res = requests.get("https://itunes.apple.com/search", params=params)
        data = res.json()

        if data.get('results') and len(data['results']) > 0:
            artwork = data['results'][0].get('artworkUrl100', '')
            if artwork:
                return artwork.replace('100x100', '600x600')
        return None
    except:
        return None


def get_song_details(track_id):
    try:
        res = requests.get(f"https://itunes.apple.com/lookup?id={track_id}")
        data = res.json()

        if data.get('results') and len(data['results']) > 0:
            track = data['results'][0]
            artwork = track.get('artworkUrl100', '')
            if artwork:
                artwork = artwork.replace('100x100', '600x600')

            return {
                "name": track.get('trackName', 'Unknown'),
                "artist": track.get('artistName', 'Unknown'),
                "album": track.get('collectionName', 'Unknown'),
                "album_art": artwork,
                "preview_url": track.get('previewUrl'),
                "spotify_url": track.get('trackViewUrl'),
                "release_date": track.get('releaseDate'),
                "duration_ms": track.get('trackTimeMillis', 0),
                "popularity": 0
            }

        return {"error": "Track not found"}
    except Exception as e:
        return {"error": str(e)}
