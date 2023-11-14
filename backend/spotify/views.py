from django.shortcuts import render, redirect
from .credentials import REDIRECT_URI, CLIENT_ID, CLIENT_SECRET
from rest_framework.views import APIView
from requests import Request, post
from rest_framework import status
from rest_framework.response import Response
from .util import *
from api.models import Room
from .models import Vote

class AuthURL(APIView):
    # Scopes URL: https://developer.spotify.com/documentation/web-api/concepts/scopes
    def get(self, request, format=None):
        scopes = "user-read-playback-state user-modify-playback-state user-read-currently-playing"

        url = Request('GET', 'https://accounts.spotify.com/authorize', params={
            'scope': scopes,
            'response_type': 'code',
            'redirect_uri': REDIRECT_URI,
            'client_id': CLIENT_ID
        }).prepare().url

        return Response({'url': url}, status=status.HTTP_200_OK)
    

def spotify_callback(request, format=None):
    code = request.GET.get('code')
    error = request.GET.get('error')

    response = post('https://accounts.spotify.com/api/token', data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }).json()

    error = response.get('error')

    check_session_exists(request)

    update_or_create_user_tokens(
        session_key = request.session.session_key, 
        access_token = response.get('access_token'), 
        token_type = response.get('token_type'), 
        expires_in = response.get('expires_in'),
        refresh_token = response.get('refresh_token')
        )
    
    return redirect("frontend:")

class IsAuthenticated(APIView):
    def get(self, request, format=None):
        is_authenticated = is_spotify_authenticated(self.request.session.session_key)
        return Response({'status': is_authenticated}, status=status.HTTP_200_OK)
    
class CurrentSong(APIView):
    def get(self, request, format=None):
        room = get_room(self.request.session)

        if not room:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        
        host = room.host
        endpoint = "player/currently-playing"
        response = execute_spotify_api_request(host, endpoint)

        if 'error' in response or 'item' not in response:
            return Response({}, status=status.HTTP_204_NO_CONTENT)
        
        item = response.get('item')
        song_id = item.get('id')

        votes = len(Vote.objects.filter(room=room, song_id=song_id))

        song = {
            'title': item.get('name'),
            'artist': get_artist_string(item.get('artists')),
            'duration': item.get('duration_ms'),
            'time': response.get('progress_ms'),
            'image_url': item.get('album').get('images')[0].get('url'),
            'is_playing': response.get('is_playing'),
            'votes': votes,
            'votes_required': room.votes_to_skip,
            'id': song_id
        }

        self.update_room_song(room, song_id)

        return Response(song, status=status.HTTP_200_OK)
    
    def update_room_song(self, room, song_id):
        current_song = room.current_song
        
        if current_song != song_id:

            # If song changed, update the record with the correct song
            room.current_song = song_id
            room.save(update_fields=['current_song'])

            # Delete vote records belonging to the room
            votes = Vote.objects.filter(room=room).delete()


class PauseSong(APIView):
    def put(self, response, format=None):
        room = get_room(self.request.session)

        if not room:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        
        if self.request.session.session_key == room.host or room.guest_can_pause:
            pause_song(room.host)
            return Response({}, status=status.HTTP_204_NO_CONTENT)
        
        return Response({}, status=status.HTTP_403_FORBIDDEN)
    

class PlaySong(APIView):
    def put(self, response, format=None):
        room = get_room(self.request.session)

        if not room:
            return Response({}, status=status.HTTP_404_NOT_FOUND)
        
        if self.request.session.session_key == room.host or room.guest_can_pause:
            play_song(room.host)
            return Response({}, status=status.HTTP_204_NO_CONTENT)
        
        return Response({}, status=status.HTTP_403_FORBIDDEN)
    

class SkipSong(APIView):
    def post(self, request, format=None):

        # Get room object
        room = get_room(self.request.session)

        if not room:
            return Response({}, status=status.HTTP_404_NOT_FOUND) 

        # Get vote object and votes needed to skip
        votes = Vote.objects.filter(room=room, song_id=room.current_song)
        votes_needed = room.votes_to_skip

        # If user is the host or if the votes >= count needed to skip, delete vote records + 
        # skip the song
        if self.request.session.session_key == room.host or len(votes) + 1 >= votes_needed:
            votes.delete()
            skip_song(room.host)
        else:
            # Else, update the vote table and save
            votes = Vote(user=self.request.session.session_key, room=room, song_id=room.current_song)
            votes.save()
        
        return Response({}, status=status.HTTP_204_NO_CONTENT)