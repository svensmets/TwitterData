import sys
from twitter.models import TwitterKeys
from twitter.TwitterTweepy import TwitterTweepy


def main(args):
    keys = TwitterKeys()
    my_tweepy = TwitterTweepy(keys)
    my_tweepy.profile_information_search(names=names, task_id=task_id, **kwargs)