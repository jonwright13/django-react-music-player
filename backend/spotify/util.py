from .models import SpotifyToken
from django.utils import timezone
from datetime import timedelta
from requests import post, put, get
from .credentials import CLIENT_ID, CLIENT_SECRET
from api.models import Room

BASE_URL = "https://api.spotify.com/v1/me/"

def get_user_tokens(session_key):
    user_tokens = SpotifyToken.objects.filter(user=session_key)
    if user_tokens.exists():
        return user_tokens[0]
    else:
        return None

def update_or_create_user_tokens(session_key, access_token, token_type, expires_in, refresh_token):
    tokens = get_user_tokens(session_key)
    expires_in = timezone.now() + timedelta(seconds=expires_in)

    if tokens:
        tokens.access_token = access_token
        tokens.refresh_token = refresh_token
        tokens.expires_in = expires_in
        tokens.token_type = token_type
        tokens.save(update_fields=['access_token', 'refresh_token', 'expires_in', 'token_type'])
    else:
        tokens = SpotifyToken(
            user=session_key, 
            access_token=access_token, 
            refresh_token=refresh_token, 
            token_type=token_type, 
            expires_in=expires_in
            )
        tokens.save()

def is_spotify_authenticated(session_key):
    tokens = get_user_tokens(session_key=session_key)
    if tokens:
        expiry = tokens.expires_in
        if expiry <= timezone.now():
            refresh_spotify_tokens(session_key)

        return True

    return False

def refresh_spotify_tokens(session_key):
    refresh_token = get_user_tokens(session_key).refresh_token 

    response = post('https://accounts.spotify.com/api/token', data={
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }).json()

    access_token = response.get('access_token')
    token_type = response.get('token_type')
    expires_in = response.get('expires_in')

    update_or_create_user_tokens(session_key, access_token, token_type, expires_in, refresh_token)

def execute_spotify_api_request(session_key, endpoint, post_=False, put_=False):
    tokens = get_user_tokens(session_key=session_key)
    header = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tokens.access_token}

    if post_:
        post(BASE_URL + endpoint, headers=header)
    if put_:
        put(BASE_URL + endpoint, headers=header)

    response = get(BASE_URL + endpoint, {}, headers=header)
    try:
        return response.json()
    except:
        return{'error': 'Issue with request'}
    
def play_song(session_key):
    return execute_spotify_api_request(session_key, "player/play", put_=True)

def pause_song(session_key):
    return execute_spotify_api_request(session_key, "player/pause", put_=True)

def get_room(session):
    room_code = session.get('room_code')
    room = Room.objects.filter(code=room_code)

    if room.exists():
        return room[0]
    else:
        return False
    
def get_artist_string(artists):
    artist_string = ""

    for i, artist in enumerate(artists):
        if i > 0:
            artist_string += ", "
        
        name = artist.get('name')
        artist_string += name
    return artist_string

def check_session_exists(request):
    if not request.session.exists(request.session.session_key):
        request.session.create()

def skip_song(session_key):
    return execute_spotify_api_request(session_key, "player/next", post_=True)