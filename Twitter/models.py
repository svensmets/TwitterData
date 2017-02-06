
class TwitterUser:
    """
    Represents a User of Twitter, not a user of the program
    """
    def __init__(self, user_id, name, screen_name, user_description, date_created, url,profile_image_url, language,
                 location, default_profile_image, verified, friends_count, followers_count, is_protected, max_followers_exceeded,
                 ):

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


class TwitterList(models.Model):
    """
    Represents a list in twitter
    A twitter_user can be a member of a list or a subscriber
    """
    list_id = models.BigIntegerField(primary_key=True)
    list_name = models.CharField(max_length=200)
    list_full_name = models.CharField(max_length=200)
    user_membership = models.ManyToManyField(TwitterUser, related_name="list_membership", blank=True)
    user_subscription = models.ManyToManyField(TwitterUser, related_name="list_subscription", blank=True)
    task_id = models.CharField(max_length=250)


class Tweet(models.Model):
    """
    Represents a tweet in twitter
    """
    tweet_id = models.BigIntegerField(primary_key=True)
    tweeter_id = models.BigIntegerField()
    tweeter_name = models.CharField(max_length=200)
    tweet_text = models.CharField(max_length=200)
    tweet_date = models.DateTimeField()
    is_retweet = models.BooleanField()
    mentions = models.CharField(max_length=200, blank=True)
    hashtags = models.CharField(max_length=200, blank=True)
    hyperlinks = models.CharField(max_length=200, blank=True)
    task_id = models.CharField(max_length=250)
    favorite_count = models.IntegerField(null=True)
    id_str = models.CharField(max_length=100, null=True)
    in_reply_to_screen_name = models.CharField(max_length=250, null=True)
    retweet_count = models.IntegerField(null=True)
    source = models.CharField(max_length=250, null=True)
    coordinates = models.CharField(max_length=100, null=True)
    quoted_status_id = models.CharField(max_length=100, null=True)


class TwitterKeys(models.Model):
    """
    The keys the user enters into the application to start a search
    """
    consumer_key = models.CharField(max_length=200)
    consumer_secret = models.CharField(max_length=200)
    access_token = models.CharField(max_length=200)
    access_token_secret = models.CharField(max_length=200)
    user = models.ForeignKey(User)


class TwitterRelationship(models.Model):
    """
    Relationship between two Twitter Users
    """
    from_user_id = models.BigIntegerField()
    to_user_id = models.BigIntegerField()
    relation_used = models.CharField(max_length=100)
    task_id = models.CharField(max_length=250)