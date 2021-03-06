###
# Copyright (c) 2017, Mike Burns
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.world as world
import supybot.ircutils as ircutils
import supybot.ircmsgs as ircmsgs
import supybot.callbacks as callbacks
import supybot.conf as conf
import supybot.schedule as schedule
import supybot.registry as registry
from trello import TrelloApi
import sys
import time
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('TrelloMon')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x

class TrelloMon(callbacks.Plugin):
    """Trello List Monitor bot"""
    threaded = True

    def __init__(self, irc):
        self.__parent = super(TrelloMon, self)
        self.__parent.__init__(irc)
        self.trello = None
        self.reload_trello()
        self.last_run = {}
        for name in self.registryValue('lists'):
            self.register_list(name)
        schedule.addPeriodicEvent(self.check_trello(irc), 30,
                    name=self.name(), now=False)
        reload(sys)

    def die(self):
        self.__parent.die()
        schedule.removeEvent(self.name())

    def debug(self, msg):
        if self.registryValue('debug'):
            print "DEBUG:  " + time.ctime() + ":  " + str(msg)

    def _send(self, message, channel, irc):
        '''send message to irc'''
        msg = ircmsgs.privmsg(channel, message)
        irc.queueMsg(msg)

    def reload_trello(self):
        self.trello = None
        self.trello = TrelloApi(self.registryValue('trelloApi'))
        self.trello.set_token(self.registryValue('trelloToken'))

    def reload(self, irc, msg, args):
        '''reload trello api'''
        self.reload_trello()
        if self.trello is not None:
            irc.replySuccess()
        else :
            irc.replyFailure()
    reloadtrello = wrap(reload, [])

    def kill(self, irc, msg, args):
        ''' kill auto-updates'''
        self.die()
    killagent = wrap(kill, ['admin'])

    def startagent(self, irc, msg, args):
        '''start the monitoring agent'''
        schedule.addPeriodicEvent(self.check_trello(irc), 20,
                    name=self.name(), now=True)
    startagent = wrap (startagent, ['admin'])

    def apikey(self, irc, msg, args):
        '''print apikey'''
        irc.reply(self.registryValue('trelloApi'))
    apikey = wrap(apikey, [])

    def register_list(self, name, trelloid=""):
        install = conf.registerGroup(conf.supybot.plugins.TrelloMon.lists,
        name.lower())

        conf.registerChannelValue(install, "AlertMessage",
            registry.String("", """Prefix for all alerts for this trello list"""))

        conf.registerGlobalValue(install, "list_id",
            registry.String(trelloid, """the trello id for the list being monitored"""))

        conf.registerChannelValue(install, "interval",
            registry.PositiveInteger(10, """The cadence for polling the board"""))

        conf.registerChannelValue(install, "verbose", registry.Boolean(True,
            """Should this list report a summary or all cards"""))

        conf.registerChannelValue(install, "active", registry.Boolean(False,
            """Should this list be reported on this channel"""))

        conf.registerGlobalValue(install, "url",
            registry.String("https://trello.com", """link quick hash to the board containing
            this list"""))
        if trelloid == "":
            trelloid = self.registryValue("lists."+name+".list_id")
        if self.trello is not None:
            url="https://trello.com/b/" + self.trello.lists.get_board(trelloid)['shortLink']
            self.setRegistryValue("lists."+name+".url", url)


    def addlist(self, irc, msg, args, name, trelloid):
        '''<name> <trello_id>
        Adds a new list that can be monitored'''
        self.register_list(name, trelloid)
        lists = self.registryValue('lists')
        lists.append(name.lower())
        self.setRegistryValue('lists',lists)
        irc.replySuccess()
    addlist = wrap(addlist, ['admin',
    'somethingwithoutspaces','somethingwithoutspaces'])

    def get_trello_cards(self, list=None, label=None):
        result=[]
        if list is None or list == "":
            return result
        for card in self.trello.lists.get_card(list):
            if label is None:
                result.append(card['name'])
            else:
                for card_label in card['labels']:
                    if label == card_label['name']:
                        result.append(card['name'])
        return result

    def check_trello(self, irc):
        '''based on plugin config, scan trello for cards in the specified lists'''
        #for each irc network in the bot
        for i in world.ircs:
            self.debug(i)
            #for each channel the bot is in
            for chan in i.state.channels:
                self.debug(chan)
                #for each list in the definition
                for entry in self.registryValue('lists'):
                    self.debug(entry)
                    #if not active in that channel (default is false), then
                    # do nothing
                    path = 'lists.' + entry + "."
                    if not self.registryValue("lists."+entry+".active."+chan):
                        self.debug("not active in chan: " + chan)
                        continue
                    #if no last_run time set, then set it
                    if entry+"_"+chan not in self.last_run:
                        self.debug("no last run")
                        self.last_run[entry+"_"+chan] = time.mktime(time.gmtime())
                    #compare last run time to current time to interval
                    # if less than interval, next
                    elif (float(time.mktime(time.gmtime()) - self.last_run[entry+"_"+chan]) <
                        float(self.registryValue("lists."+entry+".interval."+chan)
                        * 60)):
                        self.debug("last run too recent")
                        continue
                    #if greater than interval, update
                    self.debug("last run too old or no last run")
                    results = self.get_trello_cards(self.registryValue('lists.'+entry+'.list_id'))
                    if results == []:
                        self.debug("no results")
                        continue
                    # check verbose setting per channel -- defaults to false
                    # TODO add label logic
                    message = self.registryValue("lists."+entry+".AlertMessage")
                    if self.registryValue("lists."+entry+".verbose."+chan):
                        self.debug("verbose")
                        for card in results:
                            self._send(message + card, chan, irc)
                    else:
                        self.debug("not verbose")
                        self._send(message + str(len(results)) + " card(s) in " + entry, chan, irc)

    def execute_wrapper(self, irc, msgs, args):
        '''admin test script for the monitor command'''
        self.check_trello(irc)
    execute = wrap(execute_wrapper, ['admin'])

    def test(self, irc, msgs, args):
        '''test'''
        irc.reply(self.registryValue('lists.failingtest.interval'))
        irc.reply(self.registryValue('lists.failingtest.interval.#rdmb'))
        irc.reply(self.registryValue('lists.failingtest.interval.#rhos-delivery'))
    tester = wrap(test, [])


Class = TrelloMon


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
