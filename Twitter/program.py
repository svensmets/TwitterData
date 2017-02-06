import sys
from models import TwitterKeys
from TwitterTweepy import TwitterTweepy

def main(args):

    keys = TwitterKeys()
    tweepy = TwitterTweepy(keys)
