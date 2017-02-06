import logging
from twitter.models import TwitterUser, TwitterList, TwitterRelationship
from twitter.models import Tweet
from django.db import connection
from django.db.utils import OperationalError


class TwitterTweepy:
    """
    Access to twitter API with Tweepy library
    """

    def __init__(self, keys, authentication='app_level'):
        self.keys = keys
        # user app level authentication default, except for streaming (gives 401 error)
        self.authentication = authentication
        self.api = self.authenticate()
        self.logger = logging.getLogger('twitter')

    def authenticate(self):
        """
        Authenticate with Twitter API
        :return Twitter API wrapper object
        """
        # http://www.karambelkar.info/2015/01/how-to-use-twitters-search-rest-api-most-effectively./
        # using appauthhandler instead of oauthhandler, should give higher limits as stated in above link
        auth = tweepy.OAuthHandler(self.keys.consumer_key, self.keys.consumer_secret)
        auth.set_access_token(self.keys.access_token, self.keys.access_token_secret)
        return tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True, retry_count=3, retry_delay=5,
                          retry_errors=set([401, 404, 500, 503]))

    def user_exists(self, screen_name):
        """
        Check whether a name is a valid twitter username or not
        :param screen_name: name to check
        :return: true if valid username, false if invalid username
        """
        try:
            user_to_check = self.api.get_user(screen_name)
            self.logger.debug(user_to_check.screen_name + ", " + screen_name)
            if user_to_check.screen_name.lower() == screen_name.lower():
                return True
        except tweepy.TweepError:
            self.logger.debug("Tweepy: Error in user_exists")
        return False

    def get_id_of_user(self, username):
        """
        Get the id of a user by its username
        :param username: the name of the user
        :return: id of the user
        """
        user_for_id = self.api.get_user(username)
        return user_for_id.id_str

    def profile_information_search(self, names, task_id, friends=False, followers=False, max_followers={},
                                   list_memberships=False, list_subscriptions=False, relationships_checked=False):
        """ Collect the information needed to build a relationship network
            The full user objects of the friends and followers of a list of usernames is collected
            The total number of friends and followers is calculated
            The lowest number (friends or followers) is used to build the relationship table
            :param names: comma separated list of EGO names entered by user
            :param friends: boolean Friends lookup yes or no
            :param followers: boolean Followers lookup yes or no
            :param max_followers: maximum number of followers a EGO-name can have
            :param list_memberships: get the lists a user is a member of yes or no
            :param list_subscriptions: get the lists a users is subscribed on yes or no (also owned lists)
        """
        # https://dev.twitter.com/rest/reference/get/users/lookup
        # get names from list, remove empty (otherwise error)
        names_list = names.split(',')
        self.logger.debug('friends {} followers {} max followers {} listmemberships {} listsubscriptions {}'
                          .format(friends, followers, max_followers, list_memberships, list_subscriptions))
        # list of ego_users as TwitterUser-objects
        list_ego_users = list()
        # list with all EGO-users and the friends and followers of this ego users
        list_total_users = list()
        # convert names of EGO-users to twitter users objects and store
        for name in names_list:
            # string cannot not be empty
            if name:
                try:
                    user = self.api.get_user(name)
                    twitter_user = TwitterUser(user_id=user.id, name=user.name, screen_name=user.screen_name,
                                               friends_count=user.friends_count, followers_count=user.followers_count,
                                               task_id=task_id, is_protected=user.protected,
                                               user_description=user.description, date_created=user.created_at,
                                               url=user.url, profile_image_url=user.profile_image_url, language=user.lang,
                                               location=user.location, default_profile_image=user.default_profile_image,
                                               verified=user.verified)
                    if user.followers_count > max_followers:
                        # exclude EGO-user if too many followers
                        self.logger.debug("{} has too many followers".format(name))
                        twitter_user.max_followers_exceeded = True
                        names_list.remove(name)
                    elif user.protected:
                        # remove users with a protected account
                        self.logger.debug("Removing user {0} because of protected account".format(name))
                        names_list.remove(name)
                    else:
                        list_ego_users.append(twitter_user)
                        list_total_users.append(twitter_user)
                    twitter_user.save()
                except tweepy.TweepError:
                    self.logger.debug("Error in profile_information_search: error get username EGO-user")

        # Collect friends of ego-users
        if friends:
            self.logger.debug("Collect friends")
            # iterate over all ego names the user has entered
            for name in names_list:
                # check first if name is not empty
                if name:
                    self.logger.debug("Friend ids of {}".format(name))
                    # get the ego user object to save the relationsship (not full ego network)
                    ego_user = self._get_user(name, list_ego_users)
                    ids = list()
                    # get user ids of friends of user
                    while True:
                        try:
                            for friend_ids in tweepy.Cursor(self.api.friends_ids, screen_name=name).pages():
                                time.sleep(1)
                                # add ids to list of ids
                                for friend_id in friend_ids:
                                    ids.append(friend_id)
                            # get user objects from friend-ids and store in database
                            # remove doubles
                            id_set = set(ids)
                            ids_no_doubles = list(id_set)
                            for page in self._paginate(ids_no_doubles, 100):
                                self._save_users(page, task_id, list_total_users)
                            # if full ego network is not collected, save the relationships between the ego user
                            # and the friends
                            if not relationships_checked:
                                for friend_id in ids_no_doubles:
                                    relation = TwitterRelationship(from_user_id=ego_user.user_id, to_user_id=friend_id,
                                                                   relation_used="friends", task_id=task_id)
                                    relation.save()
                        except tweepy.TweepError as e:
                            # when api cannot connect, reset connection
                            self.logger.debug("Error in getfriends: {0}".format(e))
                            time.sleep(50)
                            self.api = self.authenticate()
                            continue
                        break
            self.logger.debug("End of collect friends")

        # Collect followers of ego users
        if followers:
            self.logger.debug("Collect followers")
            for name in names_list:
                # check first if name is not empty
                if name:
                    self.logger.debug("Follower ids of {}".format(name))
                    # get the ego user object to save the relationsship (not full ego network)
                    ego_user = self._get_user(name, list_ego_users)
                    ids = list()
                    # get user ids of followers of user
                    while True:
                        try:
                            for follower_ids in tweepy.Cursor(self.api.followers_ids, screen_name=name).pages():
                                time.sleep(1)
                                for follower_id in follower_ids:
                                    ids.append(follower_id)
                            # get user objects from follower-ids and store in database
                            # remove doubles
                            id_set = set(ids)
                            ids_no_doubles = list(id_set)
                            for page in self._paginate(ids_no_doubles, 100):
                                self._save_users(page, task_id, list_total_users)
                            # if full ego network is not collected, save the relationships between the ego user
                            # and the friends
                            if not relationships_checked:
                                for friend_id in ids_no_doubles:
                                    relation = TwitterRelationship(from_user_id=ego_user.user_id, to_user_id=friend_id,
                                                                   relation_used="followers", task_id=task_id)
                                    relation.save()
                        except tweepy.TweepError as e:
                            self.logger.debug("Error in get followers: {0}".format(e))
                            # reset connection when api cannot connect
                            time.sleep(50)
                            self.api = self.authenticate()
                            continue
                        break
            self.logger.debug("End of collect followers")

        if list_memberships:
            self.logger.debug("Collect list memberships")
            for name in names_list:
                if name:
                    # check first if list is not empty
                    ego_user = self._get_user(name, list_ego_users)
                    while True:
                        try:
                            for twitter_lists in tweepy.Cursor(self.api.lists_memberships, screen_name=name).pages():
                                time.sleep(1)
                                # for a many to many relationship, the object has to be saved first,
                                # then the relationship can be added
                                for twitter_list in twitter_lists:
                                    twitterlist = TwitterList(list_id=twitter_list.id, list_name=twitter_list.name,
                                                            list_full_name=twitter_list.full_name, task_id=task_id)
                                    twitterlist.save()
                                    twitterlist.user_membership.add(ego_user)
                        except tweepy.TweepError as e:
                            self.logger.debug("Error in list memberships: {}".format(e))
                            # reset connection when api cannot connect
                            time.sleep(50)
                            self.api = self.authenticate()
                            continue
                        break
            self.logger.debug("End of collect list memberships")

        # Collect lists the ego user subscribes to
        if list_subscriptions:
            self.logger.debug("Collect list subscriptions")
            for name in names_list:
                if name:
                    # check first if list is not empty
                    ego_user = self._get_user(name, list_ego_users)
                    while True:
                        try:
                            for twitter_lists in tweepy.Cursor(self.api.lists_subscriptions, screen_name=name).pages():
                                time.sleep(1)
                                for twitter_list in twitter_lists:
                                    twitterlist = TwitterList(list_id=twitter_list.id, list_name=twitter_list.name,
                                                              list_full_name=twitter_list.full_name, task_id=task_id)
                                    twitterlist.save()
                                    twitterlist.user_subscription.add(ego_user)
                        except tweepy.TweepError as e:
                            # reset connection when api cannot connect
                            self.logger.debug("Tweeperror in list subscriptions: {}".format(e))
                            time.sleep(50)
                            self.api = self.authenticate()
                            continue
                        self.logger.debug("End of collect list subscriptions")
                        break

        # list with all ids of the EGO-users, and friends and followers (to speed up lookup later)
        if relationships_checked:
            list_total_users_ids = set()
            for user in list_total_users:
                list_total_users_ids.add(user.user_id)
            # Compare the total number of friends, and the total number of followers
            # The lowest number will be used to build the relationship table
            total_friends = 0
            total_followers = 0
            self.logger.debug("Total number of users: {0}".format(len(list_total_users)))
            for user in list_total_users:
                total_friends += user.friends_count
                total_followers += user.followers_count
            if total_friends <= total_followers:
                self.logger.debug("Build relationships based on friends")
                # build friends relationshis if the total number of friends is lower or equal to the followers count
                for user in list_total_users:
                    # check if user is not protected, otherwise endless loop in resetting connection
                    if not user.is_protected:
                        list_ids = list()
                        # collect all friends ids of the user
                        # counter to avoid eternal loop
                        tweeperror_count = 0
                        while True:
                            time.sleep(20)
                            try:
                                for user_ids in tweepy.Cursor(self.api.friends_ids, user_id=user.user_id).pages():
                                    for user_id in user_ids:
                                        list_ids.append(user_id)
                            except tweepy.TweepError as e:
                                # to avoid eternal loop, break if too many tweeperrors
                                tweeperror_count += 1
                                if tweeperror_count > 20:
                                    self.logger.debug("Too much times Tweeperror in relations based on friends, break")
                                    break
                                # Sometimes an Not authorized error is thrown for some users, resulting in endless loop
                                # Catch this error and break when it happens
                                if "Not authorized" in str(e):
                                    self.logger.debug("Not authorized error in relationships based on followers")
                                    break
                                # Sometimes page does not exist error, catch and break
                                if "page does not exist" in str(e):
                                    self.logger.debug("Page does not exist error")
                                    break
                                # reset connection
                                self.logger.debug("Tweeperror in relations friends: resetting connection {}".format(e))
                                self.api = self.authenticate()
                                time.sleep(50)
                                continue
                            break
                        # remove duplicates
                        set_ids = set(list_ids)
                        list_no_duplicates = list(set_ids)
                        for user_id in list_no_duplicates:
                            if user_id in list_total_users_ids and user_id != user.user_id:
                                try:
                                    relation = TwitterRelationship(from_user_id=user.user_id, to_user_id=user_id,
                                                                   relation_used="friends", task_id=task_id)
                                    relation.save()
                                except OperationalError as e:
                                    # if MySql closes the connection: reopen connection and retry one time
                                    self.logger.debug("Operationalerror: {}".format(e))
                                    connection.close()
                                    try:
                                        relation = TwitterRelationship(from_user_id=user.user_id, to_user_id=user_id,
                                                                       relation_used="followers", task_id=task_id)
                                        relation.save()
                                    except OperationalError as e:
                                        self.logger.debug("Two times operationalerror, stop retry");
                    else:
                        self.logger.debug("User is protected")
                self.logger.debug("end of relationships friends")
            else:
                self.logger.debug("Build relationships based on followers")
                # build followers relationships if the total numbert of followers is lower than
                for user in list_total_users:
                    # check if user is not protected, otherwise endless loop in resetting connection
                    if not user.is_protected:
                        list_ids = list()
                        # collect all follower ids of the user
                        # counter to avoid eternal loop
                        tweeperror_count = 0
                        while True:
                            time.sleep(20)
                            try:
                                for user_ids in tweepy.Cursor(self.api.followers_ids, user_id=user.user_id).pages():
                                    for user_id in user_ids:
                                        list_ids.append(user_id)
                            except tweepy.TweepError as e:
                                # to avoid eternal loop, break if too many tweeperrors
                                tweeperror_count += 1
                                if tweeperror_count > 20:
                                    self.logger.debug("Too much times Tweeperror in relations based on followers, break")
                                    break
                                # Sometimes an Not authorized error is thrown for some users, resulting in endless loop
                                # Catch this error en break when it happens
                                if "Not authorized" in str(e):
                                    self.logger.debug("Not authorized error in relationships based on followers: {}".format(e))
                                    break
                                # Sometimes page does not exist error
                                if "page does not exist" in str(e):
                                    self.logger.debug("Page does not exist error")
                                    break
                                self.logger.debug("Tweeperror in relations followers, resetting connection: {}".format(e))
                                self.api = self.authenticate()
                                time.sleep(50)
                                continue
                            break
                        # remove duplicates
                        set_ids = set(list_ids)
                        list_no_duplicates = list(set_ids)
                        for user_id in list_no_duplicates:
                            if user_id in list_total_users_ids and user_id != user.user_id:
                                try:
                                    relation = TwitterRelationship(from_user_id=user.user_id, to_user_id=user_id,
                                                                   relation_used="followers", task_id=task_id)
                                    relation.save()
                                except OperationalError as e:
                                    # if MySql closes the connection: retry one time
                                    self.logger.debug("Operationalerror: {}".format(e))
                                    connection.close()
                                    try:
                                        relation = TwitterRelationship(from_user_id=user.user_id, to_user_id=user_id,
                                                                       relation_used="followers", task_id=task_id)
                                        relation.save()
                                    except OperationalError as e:
                                        self.logger.debug("Two times operationalerror, stop retry");
                    else:
                        self.logger.debug("User is protected")
                self.logger.debug("end of relationships followers")
        self.logger.debug("End of search")

    def get_tweets_searchterms_searchapi(self, query_params, task_id):
        """
        Get tweets of seven days in the past, based on a list of search terms (ex hashtags)
        :param query: list of search terms
        :param task_id: the id of the current task, used to identify the data in the database
        """
        # using the Tweepy Cursor, there might be a memory leak that crashes the program
        # TODO: check memory usage
        # http://www.karambelkar.info/2015/01/how-to-use-twitters-search-rest-api-most-effectively./

        # split the query into 10 keywords per query, they will will be connected with the OR operator
        # remove empty strings from parameters

        query_params = filter(None, query_params)
        query_strings = list()
        query_operator = " OR "
        # get date of today for until parameter
        today = time.strftime("%Y-%m-%d")
        date_today = datetime.strptime(today, "%Y-%m-%d").date()
        since = date_today - timedelta(days=7)
        # if more than 10 params, multiple queries will be necessary
        for params in self._paginate(query_params, 10):
            # join max 10 parameters with the OR operator and add quotes
            query_strings.append(query_operator.join('"{0}"'.format(param) for param in params))
        # lookup the tweets in chunks of 10 params
        for query_string in query_strings:
            '''
            self.logger.debug("Get tweets based on query string: {0}".format(query_string))
            until = date_today + timedelta(days=1)
            while True:
                try:
                    for statuses in tweepy.Cursor(self.api.search, q=query_string, since=since, until=until, count=100,
                                                include_entities=True).pages():
                        for status in statuses:
                            try:
                                self._save_tweet(status=status, task_id=task_id)
                            except:
                                self.logger.debug("Exception in save tweet")
                                continue
                        time.sleep(0.3)
                    break
                except tweepy.TweepError as e:
                    self.logger.debug("Error in searchterms {0}".format(e))
                    time.sleep(50)
                    self.authenticate()
                    continue
            self.logger.debug("No more tweets for {0}".format(query_string))
            '''
            maxTweets = 10000000 # Some arbitrary large number
            tweets_per_query = 100  # this is the max the API permits
            since_id = None
            # If results only below a specific ID are, set max_id to that ID.
            # else default to no upper limit, start from the most recent tweet matching the search query.
            max_id = -1
            tweet_count = 0
            while tweet_count < maxTweets:
                try:
                    if max_id <= 0:
                        if not since_id:
                            new_tweets = self.api.search(q=query_string, count=tweets_per_query)
                        else:
                            new_tweets = self.api.search(q=query_string, count=tweets_per_query, since_id=since_id)
                    else:
                        if not since_id:
                            new_tweets = self.api.search(q=query_string, count=tweets_per_query, max_id=str(max_id - 1))
                        else:
                            new_tweets = self.api.search(q=query_string, count=tweets_per_query,max_id=str(max_id - 1)
                                                         ,since_id=since_id)
                    if not new_tweets:
                        print("No more tweets found")
                        break
                    for tweet in new_tweets:
                        try:
                            self._save_tweet(status=tweet, task_id=task_id)
                        except:
                            self.logger.debug("Exception in save tweet")
                            continue
                    tweet_count += len(new_tweets)
                    print("Downloaded {0} tweets".format(tweet_count))
                    max_id = new_tweets[-1].id
                    time.sleep(1)
                except tweepy.TweepError as e:
                    # Just exit if any error
                    print("some error : " + str(e))
                    time.sleep(100)
                    continue

        self.logger.debug("End of search")

    def get_tweets_names_searchapi(self, query_params, task_id):
        """
        Get tweets of seven days in the past, based on a list of usernames
        :param query_params: list of user names
        :param task_id: the id of the current task, used to identify the data in the database
        """
        # add from: and to: to all usernames
        query_params = filter(None, query_params)
        query_strings = list()
        query_operator_or = " OR "
        query_operator_from = "from:"
        query_operator_to = "to:"
        for params in self._paginate(query_params, 5):
            query_strings.append(query_operator_or.join('{0}{1} OR {2}{3}'
                                                        .format(query_operator_from, param, query_operator_to, param)
                                                        for param in params))
        for query_string in query_strings:
            self.logger.debug(query_string)
            while True:
                try:
                    for statuses in tweepy.Cursor(self.api.search, q=query_string,  count=100,
                                                include_entities=True).pages():
                        for status in statuses:
                            try:
                                self._save_tweet(status=status, task_id=task_id)
                            except:
                                self.logger.debug("Error in save tweet names searchapi")
                                pass
                            time.sleep(0.3)
                except tweepy.TweepError as e:
                    self.logger.debug("Error in cursor save tweet names searchapi: {}".format(e))
                    time.sleep(50)
                    self.authenticate()
                    continue
            self.logger.debug("No more tweets for {0}".format(query_string))
        self.logger.debug("End of search")

    def get_tweets_timeline(self, names, task_id):
        """
        Get the tweets of a user using GET statuses/user_timeline
        :param names: a list of names to get the timeline of
        :param task_id: the task id needed to identify the tweets in the db
        """
        user_names = filter(None, names)
        for name in user_names:
            self.logger.debug("Timeline search of {0}".format(name))
            while True:
                try:
                    for statuses in tweepy.Cursor(self.api.user_timeline, screen_name=name).pages():
                        for status in statuses:
                            try:
                                self._save_tweet(status=status, task_id=task_id)
                            except:
                                pass
                            time.sleep(0.3)
                except tweepy.TweepError as e:
                    self.logger.debug("Error in cursor in timeline: {}".format(e))
                    time.sleep(50)
                    self.authenticate()
                    continue
        self.logger.debug("Timeline search ended")

    def collect_random_tweets(self, task_id):
        """
        Collect a number of random tweets from the search API
        :param task_id: the task id needed to identify the tweets in the db
        """
        self.logger.debug("Random tweet search started")
        query = "en OR of OR is OR het OR de"
        while True:
            try:
                for statuses in tweepy.Cursor(self.api.search, q=query, lang='nl').pages():
                    for status in statuses:
                        self._save_tweet(status=status, task_id=task_id)
            except tweepy.TweepError as e:
                self.logger.debug("Error in random tweets: {}".format(e))
                self.authenticate()
                continue
        self.logger.debug("Random tweet search ended")

    def get_ids_from_screennames(self, screennames):
        """
        Returns the id of the screenname
        :param screennames: a list of screennames
        :return: a list of ids
        """
        # GET users/lookup
        # Returns fully-hydrated user objects for up to 100 users per request,
        # as specified by comma-separated values passed to the user_id and/or screen_name parameters.

        # paginate in chunks of 100
        ids_list = list()
        for names in self._paginate(screennames, 100):
            users = self.api.lookup_users(screen_names=names)
            for user in users:
                ids_list.append(user.id_str)
        return ids_list

    def _save_users(self, ids, task_id, user_list):
        """
        converts a hundred ids of users to objects, saves them and adds them to a list
        :param ids: max 100
        :param task_id: the id of the current task, used to identify the data in the database
        :param user_list: a list the users will be added to
        """
        users = self.api.lookup_users(user_ids=ids)
        for user in users:
            twitter_user = TwitterUser(user_id=user.id, name=user.name, screen_name=user.screen_name,
                                       friends_count=user.friends_count, followers_count=user.followers_count,
                                       task_id=task_id, is_protected=user.protected,
                                       user_description=user.description, date_created=user.created_at,
                                       url=user.url, profile_image_url=user.profile_image_url, language=user.lang,
                                       location=user.location, default_profile_image=user.default_profile_image,
                                       verified=user.verified)
            twitter_user.save()
            user_list.append(twitter_user)

    def _paginate(self, iterable, page_size):
        """
        iterates over an iterable in <page size> pieces
        code from http://stackoverflow.com/questions/14265082/query-regarding-pagination-in-
        tweepy-get-followers-of-a-particular-twitter-use
        http://stackoverflow.com/questions/3744451/is-this-how-you-paginate-or-is-there-a-better-algorithm/3744531#3744531
        :param iterable: the iterable to iterate over
        :param page_size: the max page size returned
        :return: generator
        """
        while True:
            # https://docs.python.org/3.5/library/itertools.html
            # itertools.tee(iterable, n=2) Return n independent iterators from a single iterable
            # tee returns two copies of the iterable
            i1, i2 = itertools.tee(iterable)
            # start of iterable is shifted page_size times / first -> page size items placed in page
            iterable, page = (itertools.islice(i1, page_size, None), list(itertools.islice(i2, page_size)))
            if len(page) == 0:
                break
            yield page

    def _get_user(self, name, list_users):
        """
        returns the user with the username from the given list
        :param name: name of the user
        :param list_users: the list of users
        :return: TwitterUser object with the name
        """
        for user in list_users:
            self.logger.debug("get user method {} {}".format(name, user.screen_name))
            if user.screen_name.lower() == name.lower():
                return user

    def _save_tweet(self, status, task_id):
        """
        saves a tweet into the database
        :param status: the tweet
        :param task_id: the id of the current task, used to identify the data in the database
        """
        text_of_tweet = ""
        hashtags = ""
        urls = ""
        mentions = ""
        delimiter = ";"
        is_retweet = False
        status_id = 0
        # check is the tweet is a retweet
        # if it is, add is_retweet = True and get the text from the original tweet (normal text is truncated)
        if hasattr(status, 'retweeted_status'):
            text_of_tweet = status.retweeted_status.text
            is_retweet = True
        else:
            text_of_tweet = status.text
        # get mentions, urls & hashtags
        if hasattr(status, 'entities'):
            for hashtag in status.entities['hashtags']:
                hashtags += hashtag['text'] + delimiter
            for mention in status.entities['user_mentions']:
                mentions += mention['screen_name'] + delimiter
            for url in status.entities['urls']:
                urls += url['expanded_url'] + delimiter

        # avoid a Runtimewarning: convert naive to non naive datetime
        # TODO: still error maybe?
        # quoted_status_id only exists if tweet is a quoted tweet
        if hasattr(status, 'quoted_status_id'):
            status_id = status.quoted_status_id
        date_tweet = pytz.utc.localize(status.created_at)
        tweet = Tweet(tweet_id=status.id_str,
                      tweeter_id=status.user.id, tweeter_name=status.user.screen_name, tweet_text=text_of_tweet,
                      tweet_date=date_tweet, is_retweet=is_retweet,
                      mentions=mentions, hashtags=hashtags, hyperlinks=urls, task_id=task_id,
                      coordinates=status.coordinates, favorite_count=status.favorite_count, id_str=status.id_str,
                      in_reply_to_screen_name=status.in_reply_to_screen_name, retweet_count=status.retweet_count,
                      source=status.source, quoted_status_id=status_id)
        # retry if an operationalerror is thrown (deadlock)
        retry = True
        retry_times = 0
        while retry:
            try:
                tweet.save()
                retry = False
            except OperationalError as e:
                self.logger.debug("Operationalerror in save tweet {0}: retry times = {1}".format(e, retry_times))
                retry_times += 1
                if retry_times > 10:
                    self.logger.debug("Too many times OperationalError, quitting save tweet")
                    retry = False
            except UnicodeEncodeError as e:
                self.logger.debug("Unicode error in save tweet: {0}".format(e))
                retry = False
        del tweet




class TweetsStreamListener(tweepy.StreamListener):
    """
    Class for starting the stream api search based on names
    http://www.brettdangerfield.com/post/realtime_data_tag_cloud/
    http://www.rabbitmq.com/tutorials/tutorial-one-python.html
    (21/12/2015)
    """

    def __init__(self, api, task_id):
        self.api = api
        self.task_id = task_id
        self.logger = logging.getLogger('twitter')
        super(tweepy.StreamListener, self).__init__()

        # setup of rabbitMQ connection
        # connection = pika.BlockingConnection(pika.ConnectionParameters(''))
        # self.channel = connection.channel()
        # args = {"x-max-length": 2000}
        # self.channel.queue_declare(queue='twitter_toppic_feed', arguments=args)

    def on_status(self, status):
        self._save_tweet(status=status, task_id=self.task_id)

    def on_error(self, status_code):
        self.logger.debug("Error in streaming tweets by name: " + str(status_code))
        # return True

    def on_timeout(self):
        self.logger.debug("timeout")
        # return True

    def on_disconnect(self, notice):
        """
        Stream will be programmatically disconnected after a given time period
        :param notice:
        """
        return False

    def _save_tweet(self, status, task_id):
        text_of_tweet = ""
        hashtags = ""
        urls = ""
        mentions = ""
        delimiter = ";"
        is_retweet = False
        status_id = 0
        # check is the tweet is a retweet
        # if it is, add is_retweet = True and get the text from the original tweet (normal text is truncated)
        if hasattr(status, 'retweeted_status'):
            text_of_tweet = status.retweeted_status.text
            is_retweet = True
        else:
            text_of_tweet = status.text
        # get mentions, urls & hashtags
        if hasattr(status, 'entities'):
            for hashtag in status.entities['hashtags']:
                self.logger.debug(str(hashtag))
                hashtags += hashtag['text'] + delimiter
            for mention in status.entities['user_mentions']:
                self.logger.debug(str(mention))
                mentions += mention['screen_name'] + delimiter
            for url in status.entities['urls']:
                self.logger.debug(str(url))
                urls += url['expanded_url'] + delimiter

        # avoid a Runtimewarning: convert naive to non naive datetime
        date_tweet = pytz.utc.localize(status.created_at)
        if hasattr(status, 'quoted_status_id'):
            status_id = status.quoted_status_id
        tweet = Tweet(tweet_id=status.id_str,
                      tweeter_id=status.user.id, tweeter_name=status.user.screen_name, tweet_text=text_of_tweet,
                      tweet_date=date_tweet, is_retweet=is_retweet,
                      mentions=mentions, hashtags=hashtags, hyperlinks=urls, task_id=task_id,
                      coordinates=status.coordinates, favorite_count=status.favorite_count, id_str=status.id_str,
                      in_reply_to_screen_name=status.in_reply_to_screen_name, retweet_count=status.retweet_count,
                      source=status.source, quoted_status_id=status_id)
        # retry if an operationalerror is thrown (deadlock)
        retry = True
        retry_times = 0
        while retry:
            try:
                tweet.save()
                retry = False
            except OperationalError:
                self.logger.debug("Operationalerror in save tweet: retry times = {}".format(retry_times))
                retry_times += 1
                if retry_times > 10:
                    self.logger.debug("To many times OperationalError, quitting save tweet")
                    retry = False
            except UnicodeEncodeError:
                retry = False