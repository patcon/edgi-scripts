#!/usr/bin/env python

from datetime import datetime
import json
import os
import requests
from subprocess import check_output
import tempfile
from urllib.parse import urlparse
from zoomus import ZoomClient

ZOOM_API_KEY = os.environ['EDGI_ZOOM_API_KEY']
ZOOM_API_SECRET = os.environ['EDGI_ZOOM_API_SECRET']

def is_truthy(x): return x.lower() in ['true', '1', 'y', 'yes']
ZOOM_DELETE_AFTER_UPLOAD = is_truthy(os.environ.get('EDGI_ZOOM_DELETE_AFTER_UPLOAD', ''))

MEETINGS_TO_RECORD = ['EDGI Community Standup']
DEFAULT_YOUTUBE_PLAYLIST = 'Uploads from Zoom'

client = ZoomClient(ZOOM_API_KEY, ZOOM_API_SECRET)

# Assumes first id is main account
user_id = json.loads(client.user.list().text)['users'][0]['id']

def fix_date(date_string):
    date = date_string
    index = date.find('Z')
    date = date[:index] + '.0' + date[index:]

    return date

def pretty_date(date_string):
    return datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%SZ').strftime('%b %-d, %Y')

def download_file(url, download_path):
    r = requests.get(url, stream=True)
    resolved_url = r.url
    filename = urlparse(resolved_url).path.split('/')[-1]
    filepath = os.path.join(download_path, filename)
    if os.path.exists(filepath):
        r.close()
        return
    with open(filepath, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk: # filter out keep-alive new chunks
                f.write(chunk)

    return filepath

DO_FILTER = False

with tempfile.TemporaryDirectory() as tmpdirname:
    print('Creating tmp dir: ' + tmpdirname)
    meetings = client.recording.list(host_id=user_id).json()['meetings']
    meetings = sorted(meetings, key=lambda m: m['start_time'])
    meetings = filter(lambda m: m['duration'] > 1, meetings)
    for meeting in meetings:
        print('Processing recording: ' + meeting['topic'] + ' from ' + meeting['start_time'])
        # 3. filter by criteria (no-op for now)
        if meeting['topic'] not in MEETINGS_TO_RECORD and DO_FILTER:
            print('Skipping...')
            continue

        print('Recording is permitted for upload!')
        for file in meeting['recording_files']:
            if file['file_size'] == 0:
                print('Meeting still processing: {}'.format(meeting['topic']))
                break
            else:
                if file['file_type'].lower() == 'mp4':
                    url = file['download_url']
                    print('Download from ' + url + ' ...')
                    filepath = download_file(url, tmpdirname)
                    title = meeting['topic'] + ' - ' + pretty_date(meeting['start_time'])
                    command = [
                            "youtube-upload", filepath,
                            "--title=" + title,
                            "--playlist=" + DEFAULT_YOUTUBE_PLAYLIST,
                            "--recording-date=" + fix_date(meeting['start_time']),
                            "--privacy=unlisted",
                            "--client-secrets=client_secret.json",
                            "--credentials-file=.youtube-upload-credentials.json"
                            ]
                    out = check_output(command)
                    if ZOOM_DELETE_AFTER_UPLOAD:
                        # Just delete the video for now, since that takes the most storage space.
                        # We should save the chat log transcript in a comment on the video.
                        client.recording.delete(meeting_id=file['meeting_id'], file_id=file['id'])
                        print("Deleted {} file from Zoom for recording: {}".format(meeting['topic'], file['file_type']))
                    print(out)
