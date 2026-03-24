import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# using groq because its free and fast
# llama 3.3 70b is the best model they have rn
MODEL = "llama-3.3-70b-versatile"
_client = None

def get_client():
    """only create client once and reuse it"""
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


def analyze_lyrics(song_name, artist=""):
    """ask ai to break down what the song lyrics mean"""
    try:
        prompt = f"""Analyze the song "{song_name}" by {artist if artist else 'unknown artist'}.

Provide a detailed analysis including:
1. Main theme and meaning of the lyrics
2. Key emotions expressed
3. Literary devices used (metaphors, symbolism etc)
4. Cultural or historical context if any
5. Overall message the artist is trying to convey

Be insightful but keep it easy to understand. Format nicely with sections."""

        chat = get_client().chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a music expert and lyrics analyst. You have deep knowledge of songs across all genres and eras."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL,
            temperature=0.7,
            max_tokens=1024
        )

        return {
            "song": song_name,
            "artist": artist,
            "analysis": chat.choices[0].message.content
        }

    except Exception as e:
        print(f"Groq error in analyze_lyrics: {e}")
        return {"error": f"Failed to analyze: {str(e)}"}


def detect_mood(song_name, artist=""):
    """figures out the mood and vibe of a song"""
    try:
        prompt = f"""For the song "{song_name}" by {artist if artist else 'unknown artist'}, detect the mood and emotions.

Return your response as JSON with these fields:
- primary_mood: the main mood (e.g. happy, sad, energetic, romantic, melancholic)
- secondary_mood: a secondary mood if applicable
- energy_level: low, medium, or high
- emotions: list of emotions present in the song
- color_code: a hex color that represents this mood (e.g. #FF6B6B for passionate)
- description: a brief 2-3 sentence description of the mood
- best_for: when is this song best to listen to (e.g. "late night drives", "workout")

Return ONLY valid JSON, no extra text."""

        chat = get_client().chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a music mood analyst. You understand the emotional qualities of songs deeply. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL,
            temperature=0.5,
            max_tokens=512
        )

        response_text = chat.choices[0].message.content

        # groq sometimes wraps the json in ```json``` so we need to remove that
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        mood_data = json.loads(cleaned.strip())
        mood_data['song'] = song_name
        mood_data['artist'] = artist
        return mood_data

    except json.JSONDecodeError:
        # sometimes ai doesnt return proper json, just return what we got
        return {
            "song": song_name,
            "artist": artist,
            "primary_mood": "unknown",
            "description": response_text,
            "color_code": "#808080"
        }
    except Exception as e:
        print(f"mood detection error: {e}")
        return {"error": f"Failed to detect mood: {str(e)}"}


def generate_playlist(description):
    """give it a mood description and it makes a 10 song playlist"""
    try:
        prompt = f"""Based on this description: "{description}"

Generate a playlist of exactly 10 songs that match this vibe. For each song include:
- song_name
- artist
- why it fits (brief reason)
- mood

Return as a JSON object with a "playlist" array. Each item should have: song_name, artist, reason, mood.
Return ONLY valid JSON."""

        chat = get_client().chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a music curator with extensive knowledge of songs across all genres, decades, and cultures. Generate diverse and creative playlists. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL,
            temperature=0.8,
            max_tokens=1024
        )

        response_text = chat.choices[0].message.content

        # same json cleanup as detect_mood
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        playlist_data = json.loads(cleaned.strip())
        playlist_data["description"] = description
        return playlist_data

    except json.JSONDecodeError:
        return {"error": "AI returned invalid format, please try again", "raw": response_text}
    except Exception as e:
        print(f"playlist generation error: {e}")
        return {"error": f"Failed to generate playlist: {str(e)}"}


def get_insights(history):
    """looks at what you've been listening to and tells you about your taste"""
    if not history or len(history) == 0:
        return {"insights": "No listening history yet! Start identifying some songs to get personalized insights."}

    try:
        # put all the songs into a text list for the ai prompt
        songs_list = ""
        for item in history:
            songs_list += f"- {item.get('song_name', 'Unknown')} by {item.get('artist', 'Unknown')}"
            if item.get('mood'):
                songs_list += f" (mood: {item['mood']})"
            songs_list += "\n"

        prompt = f"""Here is a user's recent listening history:

{songs_list}

Analyze their listening patterns and generate fun, engaging insights. Include:
1. Their dominant mood/genre preference (with percentage estimates)
2. What their music taste says about their personality
3. A fun "music personality" title for them
4. Time-based patterns if noticeable
5. Song/artist recommendations based on their taste
6. A fun fact or observation about their listening habits

Be conversational, fun and slightly humorous. Use emojis sparingly. Make it feel personalized."""

        chat = get_client().chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a fun music analyst who gives personalized, engaging insights about people's music taste. Be conversational and insightful."},
                {"role": "user", "content": prompt}
            ],
            model=MODEL,
            temperature=0.8,
            max_tokens=1024
        )

        return {
            "insights": chat.choices[0].message.content,
            "total_songs": len(history)
        }

    except Exception as e:
        print(f"insights error: {e}")
        return {"error": f"Failed to generate insights: {str(e)}"}
