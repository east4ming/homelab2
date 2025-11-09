# Media management

!!! warning

    This is for educational purposes only :wink: Use it at your own risk!

## Initial setup

- Jellyfin `https://jellyfin.example.com`:
    - Create an `admin` user and save the credentials to your password manager
    - Add media libraries:
        - Movies at `/media/movies`
        - Shows at `/media/shows`

Optionally, for convenience, you can add a `guest` account without a password in Jellyfin,
allow access to all libraries, and allow that account to manage requests in Jellyseerr.

## Usage

Here's a suggested flow:

- Users using the `guest` account can request media in Jellyseerr
- Admins approve the request (or you can enable auto-approve)
- Wait for the media to be downloaded
- Watch on Jellyfin

You may need to increase the volume size depending on your usage.
