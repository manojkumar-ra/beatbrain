from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()

# importing my modules
from database import init_db, save_to_history, get_history
from identifier import identify_song
from analyzer import analyze_lyrics, detect_mood, generate_playlist, get_insights
from spotify_client import search_songs

app = FastAPI(
    title="BeatBrain - AI Music Intelligence",
    description="Identify songs, analyze lyrics, detect moods and get AI-powered music insights",
    version="1.0.0"
)

# allowing all origins for now, need to restrict this later
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# serve the frontend html and css and js files
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# homepage - just serves the html file
@app.get("/")
def serve_frontend():
    return FileResponse("static/index.html")


# these are the request body models for the post routes
class LyricsRequest(BaseModel):
    song_name: str
    artist: str = ""

class MoodRequest(BaseModel):
    song_name: str
    artist: str = ""

class PlaylistRequest(BaseModel):
    description: str = ""
    vibe: str = ""

class AnalyzeRequest(BaseModel):
    song_name: str
    artist: str = ""
    spotify_id: str = ""  # not using this rn but keeping for future


# when server starts, setup the database tables
@app.on_event("startup")
def startup():
    print("Starting BeatBrain...")
    init_db()


# just to check if server is alive
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "BeatBrain is running!"}


# identify song from audio file that user uploads
@app.post("/identify")
async def identify(file: UploadFile = File(...)):
    # make sure its actually an audio file
    if not file.content_type or not file.content_type.startswith('audio'):
        # some browsers send octet-stream for audio so we allow that too
        if file.content_type != 'application/octet-stream':
            raise HTTPException(status_code=400, detail="Please upload an audio file")

    try:
        audio_data = await file.read()

        if len(audio_data) == 0:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        # identify the song
        result = identify_song(audio_data)

        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])

        # save to history
        save_to_history(
            result.get('song_name', 'Unknown'),
            result.get('artist', 'Unknown'),
            result.get('album', 'Unknown')
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"identify error: {e}")
        raise HTTPException(status_code=500, detail="Something went wrong during identification")


# send song name to groq ai and get lyrics breakdown
@app.post('/analyze-lyrics')
def analyze(req: LyricsRequest):
    if not req.song_name:
        raise HTTPException(status_code=400, detail="Song name is required")

    result = analyze_lyrics(req.song_name, req.artist)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


# figure out what mood/vibe a song has
@app.post("/detect-mood")
def mood(req: MoodRequest):
    if not req.song_name:
        raise HTTPException(status_code=400, detail="Song name is required")

    result = detect_mood(req.song_name, req.artist)

    # if we got the mood, save it to history table too
    if 'primary_mood' in result and result['primary_mood'] != 'unknown':
        try:
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE history SET mood = %s WHERE song_name = %s ORDER BY identified_at DESC LIMIT 1",
                (result['primary_mood'], req.song_name)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"couldn't update mood in history: {e}")

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


# ai generates a playlist based on what mood the user describes
@app.post("/generate-playlist")
def playlist(req: PlaylistRequest):
    if not req.description:
        raise HTTPException(status_code=400, detail="Description is required")

    result = generate_playlist(req.description)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


# show what songs the user has identified before
@app.get("/history")
def history():
    results = get_history()
    return {"history": results, "count": len(results)}


# ai looks at your history and tells you about your music taste
@app.get("/insights")
def insights():
    history_data = get_history()
    result = get_insights(history_data)
    return result


# search for songs using itunes api
@app.get("/search/{query}")
def search(query: str):
    if not query or len(query.strip()) == 0:
        raise HTTPException(status_code=400, detail="Search query is required")

    result = search_songs(query)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


# ============================================
# these are the api routes the frontend calls
# ============================================

@app.get("/api/search")
def api_search(q: str = ""):
    if not q or len(q.strip()) == 0:
        return {"results": []}
    result = search_songs(q)
    if "error" in result:
        return {"results": []}
    return result


@app.post("/api/identify")
async def api_identify(audio: UploadFile = File(...)):
    try:
        audio_data = await audio.read()
        if len(audio_data) == 0:
            return {"success": False, "message": "Empty file"}

        result = identify_song(audio_data)
        if "error" in result:
            return {"success": False, "message": result["error"]}

        # save to history
        save_to_history(
            result.get('song_name', 'Unknown'),
            result.get('artist', 'Unknown'),
            result.get('album', 'Unknown')
        )

        return {
            "success": True,
            "song": {
                "name": result.get('song_name', 'Unknown'),
                "artist": result.get('artist', 'Unknown'),
                "album": result.get('album', 'Unknown'),
                "album_art": result.get('album_art'),
                "spotify_url": result.get('spotify_url'),
                "preview_url": result.get('preview_url')
            }
        }
    except Exception as e:
        print(f"api identify error: {e}")
        return {"success": False, "message": str(e)}


# this one does both mood detection + lyrics analysis in one call
@app.post("/api/analyze")
def api_analyze(req: AnalyzeRequest):
    print(f"analyzing song: {req.song_name} by {req.artist}")

    # do mood first since its faster (less tokens)
    mood_result = detect_mood(req.song_name, req.artist)
    print(f"mood result keys: {mood_result.keys()}")

    # small gap so groq doesnt rate limit us
    import time
    time.sleep(1)

    lyrics_result = analyze_lyrics(req.song_name, req.artist)
    print(f"lyrics result keys: {lyrics_result.keys()}")

    if "error" in lyrics_result and "error" in mood_result:
        return {"success": False, "message": "Could not connect to AI service"}

    # update mood in history
    if 'primary_mood' in mood_result:
        try:
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE history SET mood = %s WHERE song_name = %s ORDER BY identified_at DESC LIMIT 1",
                (mood_result.get('primary_mood', ''), req.song_name)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except:
            pass

    return {
        "success": True,
        "mood": mood_result,
        "lyrics_analysis": lyrics_result.get("analysis", lyrics_result.get("error", "Could not analyze")),
        "similar_songs": mood_result.get("best_for", "")
    }


@app.post("/api/playlist")
def api_playlist(req: PlaylistRequest):
    try:
        vibe = req.vibe or req.description
        if not vibe:
            return {"success": False, "message": "Describe your vibe!"}

        result = generate_playlist(vibe)
        if "error" in result:
            return {"success": False, "message": result["error"]}

        # get album art for each song from itunes
        tracks = []
        for song in result.get("playlist", []):
            song_name = song.get("song_name", "Unknown")
            artist = song.get("artist", "Unknown")

            # fetch cover image
            album_art = None
            try:
                from spotify_client import get_album_art
                album_art = get_album_art(song_name, artist)
            except:
                pass

            tracks.append({
                "name": song_name,
                "artist": artist,
                "reason": song.get("reason", ""),
                "mood": song.get("mood", ""),
                "album_art": album_art
            })

        return {"success": True, "tracks": tracks}
    except Exception as e:
        print(f"api playlist error: {e}")
        return {"success": False, "message": str(e)}


@app.get("/api/insights")
def api_insights():
    history_data = get_history()
    result = get_insights(history_data)
    if "error" in result:
        return {"success": False, "message": result["error"]}
    return {"success": True, "insights": result.get("insights", ""), "total_songs": result.get("total_songs", 0)}


@app.get("/api/history")
def api_history():
    results = get_history()
    return {"history": results, "count": len(results)}


# run it
if __name__ == "__main__":
    import uvicorn
    print("starting beatbrain on port 8000...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
