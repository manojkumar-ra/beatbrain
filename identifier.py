import os
import requests
from dotenv import load_dotenv

load_dotenv()

# uses audd.io api to identify songs from audio
# acrcloud is there as backup but audd works better honestly

def identify_song(audio_data):
    """takes audio bytes and tries to figure out what song it is"""

    # audd works most of the time
    result = try_audd(audio_data)
    if result and 'error' not in result:
        return result

    # if audd fails try acrcloud
    result = try_acrcloud(audio_data)
    if result and 'error' not in result:
        return result

    return {"error": "Could not identify song. Try a clearer audio clip."}


def try_audd(audio_data):
    """send audio to audd.io and see if it finds a match"""
    try:
        print(f"audd: sending {len(audio_data)} bytes...")

        # send the audio file to audd
        data = {
            'return': 'apple_music,spotify',
        }

        # token is optional, works without it but limited requests
        api_token = os.getenv('AUDD_API_TOKEN')
        if api_token:
            data['api_token'] = api_token

        files = {
            'file': ('audio.wav', audio_data, 'audio/wav')
        }

        res = requests.post('https://api.audd.io/', data=data, files=files, timeout=25)
        print(f"audd response status: {res.status_code}")

        res_json = res.json()
        print(f"audd result: {str(res_json)[:300]}")

        if res_json.get('status') == 'success' and res_json.get('result'):
            song = res_json['result']

            # grab album cover from itunes
            album_art = None
            try:
                from spotify_client import get_album_art
                album_art = get_album_art(song.get('title', ''), song.get('artist', ''))
            except:
                pass

            # check if spotify link came back
            spotify_url = None
            try:
                sp = song.get('spotify', {})
                if sp and sp.get('external_urls'):
                    spotify_url = sp['external_urls'].get('spotify')
            except:
                pass

            return {
                'song_name': song.get('title', 'Unknown'),
                'artist': song.get('artist', 'Unknown'),
                'album': song.get('album', 'Unknown'),
                'score': 95,
                'album_art': album_art,
                'spotify_url': spotify_url,
                'preview_url': song.get('song_link')
            }
        else:
            error_msg = res_json.get('error', {}).get('error_message', 'no match found')
            print(f"audd error: {error_msg}")
            return {"error": error_msg}

    except requests.exceptions.Timeout:
        print("audd timeout")
        return {"error": "timeout"}
    except Exception as e:
        print(f"audd error: {e}")
        return {"error": str(e)}


def try_acrcloud(audio_data):
    """backup identification using acrcloud (needs paid account tho)"""
    import hmac, hashlib, base64, time

    host = os.getenv('ACRCLOUD_HOST')
    access_key = os.getenv('ACRCLOUD_ACCESS_KEY')
    access_secret = os.getenv('ACRCLOUD_ACCESS_SECRET')

    if not all([host, access_key, access_secret]):
        return {"error": "acrcloud not configured"}

    try:
        http_method = "POST"
        http_uri = "/v1/identify"
        data_type = "audio"
        signature_version = "1"
        timestamp = str(int(time.time()))

        string_to_sign = "\n".join([
            http_method, http_uri, access_key,
            data_type, signature_version, timestamp
        ])

        hashed = hmac.new(
            access_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha1
        )
        sign = base64.b64encode(hashed.digest()).decode('utf-8')

        files = {'sample': ('audio.wav', audio_data, 'audio/wav')}
        data = {
            'access_key': access_key,
            'data_type': data_type,
            'signature_version': signature_version,
            'signature': sign,
            'sample_bytes': str(len(audio_data)),
            'timestamp': timestamp
        }

        print(f"acrcloud: trying identification...")
        res = requests.post(f"https://{host}/v1/identify", files=files, data=data, timeout=20)
        res_json = res.json()

        if res_json.get('status', {}).get('code') == 0:
            music = res_json['metadata']['music'][0]

            album_art = None
            try:
                from spotify_client import get_album_art
                album_art = get_album_art(
                    music.get('title', ''),
                    music.get('artists', [{}])[0].get('name', '')
                )
            except:
                pass

            return {
                'song_name': music.get('title', 'Unknown'),
                'artist': music.get('artists', [{}])[0].get('name', 'Unknown'),
                'album': music.get('album', {}).get('name', 'Unknown'),
                'score': music.get('score', 0),
                'album_art': album_art,
                'spotify_url': None,
                'preview_url': None
            }
        else:
            msg = res_json.get('status', {}).get('msg', 'error')
            print(f"acrcloud error: {msg}")
            return {"error": msg}

    except Exception as e:
        print(f"acrcloud error: {e}")
        return {"error": str(e)}
