import urllib
import urllib2
import cookielib
import re
import yaml
import xml.sax.saxutils as saxutils
import htmlentitydefs
import ircbot
import simplejson as json
from twython.twython import Twython, TwythonError

server = 'localhost'
port = 6667
channel = '#deepshell'
botnick = 'cognito'
name = 'in cognito'
admin = 'sleeper'

score_filename = 'scores.yaml'
alias_filename = 'alias.yaml'

class Cognito(ircbot.SingleServerIRCBot):

    lastnick = None
    calls = {}
    pros = {}
    noobs = {}
    aliases = {}
    guesses = {}

    admin_commands = [
        'addalias',
        'userlist',
    ]

    commands = [
        'call',
        'cognito', 'help',
        'me',
        'score', 'scores',
        'teet',
        # 'tweet', (disabled due to privacy concerns)
    ]

    user_agent = {
        'User-agent':'Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)',
    }

    def on_welcome(self, connection, event):
        self.load_score()

        alias_file = open(alias_filename, 'r+')
        self.aliases = yaml.load(alias_file)

        connection.join(channel)

    # contains line parsing and all queries
    def on_pubmsg(self, connection, event):
        # ignore everything i say
        if event.source().split('!')[0] == botnick:
            return

        line = event.arguments()[0]

        # yubnub query
        ynterm = re.search(r"\}(.+?)\{", line)
        if ynterm != None:
            self.yubnub_query(ynterm.group(1))

        # google i'm feeling lucky query
        iflterm = re.search(r"\](.+?)\[", line)
        if iflterm != None:
            self.google_query(iflterm.group(1))

        # twitter user query
        # for some reason, start/end of line matches !\S, but doesn't match =\s
        # twituser = re.search(r"(?<!\S)@(\w+)(?!\S)", line)
        # if twituser != None:
        #     searchterm = re.search(r"\?(\w+)", line)
        #     if searchterm != None:
        #         searchterm = searchterm.group(1)
        #     self.twitteruser_query(twituser.group(1), searchterm)

        # twitter tag query
        # twittag = re.search(r"(?<!\S)#\w+(?!\S)", line)
        # if twittag != None and twittag.group() != '#ds':
        #     self.twittertag_query(twittag.group())

        # reddit api search (hack)
        redditterm = re.search(r"(?<!\S)http://www.reddit.com/(\S+)(?!\S)",
                               line)
        if redditterm != None:
            self.reddit_query(redditterm.group())

    # event handler to publicize private messages or execute private commands
    def on_privmsg(self, connection, event):
        sender = event.source().split('!')[0]

        # ignore everything i say (just in case)
        if sender == botnick:
            return

        # account for people trolling outside channel
        if sender not in self.channels[channel].userdict \
            and '~' + sender not in self.channels[channel].userdict:
            msg = sender + ' is trying to be too incognito.'
            connection.notice(channel, msg)
            return

        line = event.arguments()[0]
        command, sep, argument = line.strip().partition(' ')
        command = command.lower()
        if command[0] == '!' or command == '/me':
            command = command[1:]
        else:
            command = ''

        # if the command exists, call it
        if command in self.commands \
            or (sender == admin and command in self.admin_commands):
            command_func = getattr(self, "_" + command)
            command_func(sender, argument)
        else:
            self.lastnick = sender
            self.guesses = {}
            connection.privmsg(channel, line)

    # event handler to publicize private actions
    def on_action(self, connection, event):
        if event.target().split('!')[0] == botnick: 
            self.lastnick = event.source().split('!')[0]
            self.guesses = {}
            line = event.arguments()[0]
            if len(line) > 0:
                connection.action(channel, line)

    # admin commands
    def _addalias(self, sender, argument):
        """!addalias - add an alias for an irc user"""
        if sender == admin: # only admin allowed to do this
            name, alias = argument.split(' ')
            if name not in self.aliases:
                self.aliases[name] = [alias]
            elif alias not in self.aliases[name]:
                self.aliases[name].append(alias)
            self.save_aliases()

    def _userlist(self, sender, argument):
        """!userlist [userdict/operdict/voiceddict] - debug message """ \
        """listing users in channel"""
        if sender == admin:
            if len(argument) > 0:
                udict = argument
            else:
                udict = 'userdict'
            for name in getattr(self.channels[channel], udict):
                self.connection.notice(sender, name)

    # commands

    def _call(self, sender, argument):
        """!call <nick> - guess who said the last line in cognito"""
        self.load_score()
        propername = self.get_name(sender)
        if propername not in self.guesses:
            self.guesses[propername] = 1
        else:
            self.guesses[propername] = self.guesses[propername] + 1

        if self.get_name(self.lastnick) == propername:
            msg = 'you may not call when you were in cognito last.'
            self.connection.notice(sender, msg)
            return
        elif self.lastnick == None:
            self.connection.notice(sender, 'no one is in cognito.')
        elif self.guesses[propername] > 1:
            self.connection.notice(sender, 'you have already used your guess.')
        elif argument == self.get_name(self.lastnick):
            self.add_score(self.calls, propername)
            self.add_score(self.pros, propername)
            self.add_score(self.noobs, argument)
            self.save_score()

            msg = argument + ' owned by ' + propername
            self.connection.notice(channel, msg)
            self.lastnick = None
        else:
            self.add_score(self.calls, propername)
            self.save_score()

            msg = 'you do not know ' + argument + ' at all.'
            self.connection.notice(sender, msg)
            msg = sender + ' guessed ' + argument +'.'
            self.connection.notice(self.lastnick, msg)

    def _cognito(self, sender, argument):
        """!cognito/!help - this message"""
        self._help(sender, argument)

    def _help(self, sender, argument):
        helpmsg = [ \
            '- cognito help -',
            'cognito is an anonymizer bot for ' + channel,
            'type anything to me to have it appear in channel',
            'commands:',
        ]
        for line in helpmsg:
            self.connection.notice(sender, line)
        for command in self.commands:
            func = getattr(self, "_" + command)
            if func.__doc__ != None and len(func.__doc__) > 0:
                self.connection.notice(sender, func.__doc__)
        if sender == admin:
            self.connection.notice(sender, "admin commands:")
            for command in self.admin_commands:
                func = getattr(self, "_" + command)
                if func.__doc__ != None and len(func.__doc__) > 0:
                    self.connection.notice(sender, func.__doc__)

    def _me(self, sender, argument):
        self.lastnick = sender
        self.guesses = {}
        self.connection.action(channel, argument)

    def _score(self, sender, argument):
        """!score [calls, noobs, pros] - check the current score"""
        self._scores(sender, argument)

    def _scores(self, sender, argument):
        self.load_score()

        if len(argument) == 0:
            self.connection.notice(sender, '- scores -')
            for nick in self.calls:
                successes = 0
                if nick in self.pros:
                    successes = self.pros[nick]
                msg = '%s: %0.3f' % \
                    (nick, float(successes) /  float(self.calls[nick]))
                self.connection.notice(sender, msg)
        elif argument in ('calls', 'pros', 'noobs'):
            score = eval('self.' + argument)
            self.connection.notice(sender, '- %s -' % (argument))
            for nick in score:
                msg = '%s: %i' % (nick, score[nick])
                self.connection.notice(sender, msg)

    def _teet(self, sender, argument):
        msg = 'look at all you %s babes... ' % (argument)
        msg = msg + 'trying to suckle from the juiciest teet, switching '
        msg = msg + 'back and forth trying to make sure you *got it*'
        self.connection.notice(channel, msg)

    def _tweet(self, sender, argument):
        """!tweet <msg> - posts msg to twitter user cogshell (disabled due
            to privacy concerns)"""
        # t_api = Twython(username=t_user, password=t_pass)

        if len(argument) > 140:
            cropped = argument[140:]
            msg = 'tweet is ' + str(len(argument) - 140) + ' '
            msg = msg + 'characters too long, and has not been sent.  '
            msg = msg + 'the following should be removed:'
            self.connection.notice(sender, msg)
            self.connection.notice(sender, cropped)
            return

        # t_api.updateStatus(argument)
        msg = 'your tweet has not been posted (until sleeper gets off his ass)'
        self.connection.notice(sender, msg)

    def yubnub_query(self, query):
        query = query.replace(' ', '+')
        yubnub_url = 'http://yubnub.org/parser/parse?command=%s' % query
        try:
            req = urllib2.Request(yubnub_url, None, self.user_agent)
            handle = urllib2.urlopen(req)
            self.connection.privmsg(channel, handle.geturl())
        except:
            pass

    def google_query(self, query):
        cookiejar = cookielib.LWPCookieJar()
        opener = urllib2.build_opener(
            urllib2.HTTPCookieProcessor(cookiejar))
        urllib2.install_opener(opener)

        search_url = 'http://www.google.com/search'

        search_params = urllib.urlencode({'q':query,
                                          'btnI':'submit',
                                          'sourceid':'navclient'})
        req = urllib2.Request(search_url + '?' + search_params, None,
                              self.user_agent)
        req.add_header('Accept', '*/*')
        try:
            handle = urllib2.urlopen(req)
            self.connection.privmsg(channel, query + ': ' + handle.geturl())
        except urllib2.HTTPError:
            self.connection.notice(channel,
                                   '\'' + query + '\' returned error.')

    def twitteruser_query(self, user, search):
        t_api = Twython()
        htmlentities = dict(
            map(lambda (key, value):
            ('&' + str(key) + ';', value), htmlentitydefs.entitydefs.items())
        )
        try:
            unitext = ''
            if search != None:
                query = search + ' from:' + user
                tweetlist = t_api.searchTwitter(q=query, rpp='1')
                if len(tweetlist['results']) > 0:
                    unitext = tweetlist['results'][0]['text']
                # else:
                #     tweetlist = t_api.getUserTimeline(screen_name=user,
                #                                       count='200',
                #                                       page='1')
                #     for tweet in tweetlist:
                #         if tweet['text'].lower().find(
                #             search.lower()) > -1:
                #             unitext = tweet['text']
                #             break
            else:
                tweetlist = t_api.getUserTimeline(screen_name=user,
                                                  count='1')
                unitext = tweetlist[0]['text']

            if len(unitext) > 0:
                msg = user + ': '
                msg = msg + saxutils.unescape(
                    unitext.encode("utf-8"), htmlentities)
                msg = msg.replace('\n', ' ')
                self.connection.notice(channel, msg)

        except (TwythonError, IndexError, KeyError, urllib2.HTTPError,
                urllib2.URLError) as e:
            print 'exception while retrieving user: ' + user
            print type(e)
            print e

    def twittertag_query(self, tag):
        t_api = Twython()
        htmlentities = dict(
            map(lambda (key, value):
            ('&' + str(key) + ';', value), htmlentitydefs.entitydefs.items())
        )
        try:
            result = t_api.searchTwitter(q=tag, rpp='1')['results'][0]
            unitext = result['text']
            author = result['from_user']

            msg = author + ': ' + saxutils.unescape(
                unitext.encode("utf-8"), htmlentities)
            msg = msg.replace('\n', ' ')
            self.connection.notice(channel, msg)
        except (TwythonError, IndexError, urllib2.HTTPError,
                urllib2.URLError, UnicodeDecodeError) as e:
            print 'exception while searching for tag: ' + tag
            print type(e)
            print e

    def reddit_query(self, query, sender=None):
        try:
            if len(query) > 1 and query[-1:] != "/":
                query = query + "/"
            query = query + ".json"

            resp = json.load(urllib.urlopen(query))

            msg = u''
            if type(resp) == dict:
                return

            author = u''
            title = u''
            body = u''
            if len(resp) > 1 and len(resp[1]['data']['children']) == 1:
                author = resp[1]['data']['children'][0]['data']['author']
                body = resp[1]['data']['children'][0]['data']['body']
            else:
                title = '(' + \
                    resp[0]['data']['children'][0]['data']['title'] + ') '
                author = resp[0]['data']['children'][0]['data']['author']
                body = resp[0]['data']['children'][0]['data']['selftext']

            msg = author + ': ' + title + body
            # msg = msg.encode('utf-8')

            msg = msg.replace('\n', ' ')
            if len(msg) > 464:
                msg = msg[:461] + '...'

            if sender != None:
                self.connection.notice(sender, msg)
            else:
                self.connection.notice(channel, msg)
        except (ValueError) as e:
            print 'exception while loading url: ' + query
            print type(e)
            print e

    def add_score(self, score, nick):
        if nick in score:
            score[nick] = score[nick]+1
        else:
            score[nick] = 1

    def save_score(self):
        score_file = open(score_filename, 'w')
        yaml.dump((self.calls, self.pros, self.noobs), score_file)

    def load_score(self):
        score_file = open(score_filename, 'r+')
        (self.calls, self.pros, self.noobs) = yaml.load(score_file)

    def save_aliases(self):
        alias_file = open(alias_filename, 'w')
        yaml.dump(self.aliases, alias_file)

    def get_name(self, alias):
        for name in self.aliases:
            if alias in self.aliases[name]:
                 return name
        return alias

bot = Cognito([(server, port)], botnick, name)
bot.start()
