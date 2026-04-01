# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import tweepy
import os

client = tweepy.Client(
    consumer_key=os.environ["X_CONSUMER_KEY"],
    consumer_secret=os.environ["X_CONSUMER_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)

# Look up the user
user = client.get_user(username="bhavye_khetan")
recipient_id = user.data.id

# Send DM
client.create_direct_message(participant_id=recipient_id, text="Hi Bhavye, I saw your post about hiring MLEs in Gurgaon. I'm interested — here's my resume: https://drive.google.com/file/d/1XHvR18eazgLFTFDxOPuYeElwHmsFB6zG/view\n\nWould love to chat further!")
print(f"DM sent to @bhavye_khetan")
