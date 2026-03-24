import os
import requests
import wave
import struct
import array
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

# shazam for song recognition, audd as backup


def convert_to_raw_pcm(audio_data):
    """shazam needs raw 16khz mono pcm, this converts any audio format to that"""
    try:
        import imageio_ffmpeg
        import subprocess
        import tempfile

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        # save audio to temp file
        with tempfile.NamedTemporaryFile(suffix='.audio', delete=False) as tmp_in:
            tmp_in.write(audio_data)
            tmp_in_path = tmp_in.name

        tmp_out_path = tmp_in_path + '.raw'

        # use ffmpeg to convert to raw 16khz mono 16-bit PCM
        # ffmpeg handles any input format (mp3, wav, webm, ogg, etc)
        result = subprocess.run([
            ffmpeg_exe, '-y', '-i', tmp_in_path,
            '-ar', '16000', '-ac', '1', '-f', 's16le',
            tmp_out_path
        ], capture_output=True, text=True, timeout=15)

        if not os.path.exists(tmp_out_path) or os.path.getsize(tmp_out_path) == 0:
            print(f"ffmpeg conversion failed: {result.stderr[:300]}")
            os.unlink(tmp_in_path)
            return None

        # read raw pcm bytes
        with open(tmp_out_path, 'rb') as f:
            raw_pcm = f.read()

        # clean up
        os.unlink(tmp_in_path)
        os.unlink(tmp_out_path)

        # convert bytes to array of 16-bit signed integers
        samples = array.array('h', raw_pcm)
        print(f"ffmpeg converted: {len(samples)} samples ({len(samples)/16000:.1f}s)")
        return samples

    except Exception as e:
        print(f"audio conversion error: {e}")
        return None


def identify_song(audio_data):

    # try shazam first - its free and unlimited
    result = try_shazam(audio_data)
    if result and 'error' not in result:
        return result

    # if shazam fails try audd as backup
    result = try_audd(audio_data)
    if result and 'error' not in result:
        return result

    return {"error": "Could not identify song. Try a clearer audio clip."}


def try_shazam(audio_data):
    try:
        from ShazamAPI.algorithm import SignatureGenerator
        from ShazamAPI.signature_format import DecodedMessage
        import uuid
        import time as time_module

        print(f"shazam: processing {len(audio_data)} bytes...")

        # convert audio to raw pcm samples (16khz mono 16-bit)
        samples = convert_to_raw_pcm(audio_data)
        if samples is None:
            return {"error": "couldnt process audio format"}

        print(f"shazam: got {len(samples)} samples, generating fingerprint...")

        # create signature from the raw samples
        signature_generator = SignatureGenerator()
        signature_generator.feed_input(samples)
        signature_generator.MAX_TIME_SECONDS = 8

        # skip ahead if audio is long
        duration_seconds = len(samples) / 16000
        if duration_seconds > 12 * 3:
            signature_generator.samples_processed += 16000 * (int(duration_seconds / 16) - 6)

        # try to get a match from shazam
        API_URL = 'https://amp.shazam.com/discovery/v5/en/US/iphone/-/tag/%s/%s?sync=true&webv3=true&sampling=true&connected=&shazamapiversion=v3&sharehub=true&hubv5minorversion=v5.1&hidelb=true&video=v3'
        HEADERS = {
            "X-Shazam-Platform": "IPHONE",
            "X-Shazam-AppVersion": "14.1.0",
            "Accept": "*/*",
            "Accept-Language": "en",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "Shazam/3685 CFNetwork/1197 Darwin/20.0.0"
        }

        while True:
            signature = signature_generator.get_next_signature()
            if not signature:
                break

            # send fingerprint to shazam
            data = {
                'timezone': 'Asia/Kolkata',
                'signature': {
                    'uri': signature.encode_to_uri(),
                    'samplems': int(signature.number_samples / signature.sample_rate_hz * 1000)
                },
                'timestamp': int(time_module.time() * 1000),
                'context': {},
                'geolocation': {}
            }

            url = API_URL % (str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper())
            res = requests.post(url, headers=HEADERS, json=data, timeout=10)
            result = res.json()

            if result.get('matches'):
                track = result['track']
                title = track.get('title', 'Unknown')
                artist = track.get('subtitle', 'Unknown')

                # get album art from shazam response
                album_art = None
                try:
                    images = track.get('images', {})
                    album_art = images.get('coverarthq') or images.get('coverart')
                except:
                    pass

                # if no album art from shazam, try itunes
                if not album_art:
                    try:
                        from spotify_client import get_album_art
                        album_art = get_album_art(title, artist)
                    except:
                        pass

                # get apple music link
                song_url = track.get('url')

                # try to get album name from metadata
                album = 'Unknown'
                try:
                    sections = track.get('sections', [])
                    if sections and sections[0].get('metadata'):
                        for meta in sections[0]['metadata']:
                            if meta.get('title', '').lower() == 'album':
                                album = meta.get('text', 'Unknown')
                                break
                except:
                    pass

                print(f"shazam found: {title} by {artist}")

                return {
                    'song_name': title,
                    'artist': artist,
                    'album': album,
                    'score': 95,
                    'album_art': album_art,
                    'spotify_url': song_url,
                    'preview_url': None
                }

        print("shazam: no matches found")
        return {"error": "shazam couldnt find a match"}

    except Exception as e:
        print(f"shazam error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


def try_audd(audio_data):
    try:
        print(f"audd: sending {len(audio_data)} bytes...")

        data = {
            'return': 'apple_music,spotify',
        }

        # token is optional, works without it but very limited
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
