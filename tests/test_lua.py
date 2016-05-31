#!/usr/bin/env python
# coding=utf-8
from __future__ import unicode_literals, absolute_import, division, print_function

import pytest
import re

from sopel_modules.lua import lua
from sopel.trigger import PreTrigger, Trigger
from sopel.test_tools import MockSopel, MockSopelWrapper
from sopel.tools import Identifier, get_command_regexp
from sopel.module import VOICE


@pytest.fixture
def sopel():
    bot = MockSopel('Sopel')
    bot.config.core.owner = 'Bar'
    return bot


@pytest.fixture
def bot(sopel):
    def build_wrapper(pretrigger):
        bot = MockSopelWrapper(sopel, pretrigger)
        bot.privileges = dict()
        bot.privileges[Identifier('#Sopel')] = dict()
        bot.privileges[Identifier('#Sopel')][Identifier('Foo')] = VOICE
        bot.db = {}
        return bot
    return build_wrapper


@pytest.fixture
def pretrigger():
    def build_line(val):
        val = ':Foo!foo@example.com PRIVMSG #Sopel :' + val
        return PreTrigger(Identifier('Foo'), val)
    return build_line


def test_basic_lua(bot, pretrigger):
    msg = '.lua print("test")'
    line = pretrigger(msg)
    bot = bot(line)
    cmd = re.compile(get_command_regexp('\.', 'lua'))
    lua.lua_cmd(bot, Trigger(bot.config, line, cmd.match(msg)))


if __name__ == '__main__':
    pytest.main()
