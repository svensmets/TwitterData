
class TwitterUser:
    """
    Represents a User of Twitter, not a user of the program
    """
    def __init__(self, user_id, name, screen_name, user_description, date_created, url,profile_image_url, language,
                 location, default_profile_image, verified, friends_count, followers_count, is_protected, max_followers_exceeded):

        self.user_id = user_id
        self.name = name
        self.screen_name = screen_name
        self.user_description = user_description
        self.date_created = date_created
        self.url = url
        self.profile_image_url = profile_image_url
        self.language = language
        self.location = location
        self.default_profile_image = default_profile_image
        self.verified = verified
        self.friends_count = friends_count
        self.followers_count = followers_count
        # protected accounts cannot be accessed
        self.is_protected = is_protected
        # when the twitteruser has too many followers, account is ignored
        self.max_followers_exceeded = max_followers_exceeded
        # date_added = models.DateTimeField(auto_now=True)


class TwitterList:
    """
    Represents a list in twitter
    A twitter_user can be a member of a list or a subscriber
    """
    def __init__(self, list_id, list_name, list_full_name, user_membership, user_subscription):
        self.list_id = list_id
        self.list_name = list_name
        self.list_full_name = list_full_name
        self.user_membership = user_membership
        self.user_subscription = user_subscription


class Tweet:
    """
    Represents a tweet in twitter
    """
    def __init__(self, tweet_id, tweeter_id, tweeter_name, tweet_text, tweet_date, is_retweet, mentions, hashtags,
                 hyperlinks, favorite_count, id_str, in_reply_to_screen_name, retweet_count, source, coordinates,
                 quoted_status_id):
        self.tweet_id = tweet_id
        self.tweeter_id = tweeter_id
        self.tweeter_name = tweeter_name
        self.tweet_text = tweet_text
        self.tweet_date = tweet_date
        self.is_retweet = is_retweet
        self.mentions = mentions
        self.hashtags = hashtags
        self.hyperlinks = hyperlinks
        self.favorite_count = favorite_count
        self.id_str = id_str
        self.in_reply_to_screen_name = in_reply_to_screen_name
        self.retweet_count = retweet_count
        self.source = source
        self.coordinates = coordinates
        self.quoted_status_id = quoted_status_id


class TwitterKeys:
    """
    The keys the user enters into the application to start a search
    """
    def __init__(self, consumer_key, consumer_secret, access_token, access_token_secret, user):

        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.user = user


class TwitterRelationship:
    """
    Relationship between two Twitter Users
    """
    def __init__(self, from_user_id, to_user_id, relation_used):

        from_user_id = from_user_id
        to_user_id = to_user_id
        relation_used = relation_used