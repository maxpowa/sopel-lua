# coding=utf-8

from __future__ import unicode_literals, absolute_import, division, print_function

from sopel import module
from sopel.logger import get_logger
import os
import lupa
import json


LOGGER = get_logger('lua')


def configure(config):
    pass


def setup(bot):
    dirname = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox')
    try:
        os.mkdir(dirname)
    except OSError as e:
        pass


class TriggerWrapper:
    def __init__(self, trigger):
        self._trigger = trigger


    def __getattr__(self, name):
        try:
            return getattr(self._trigger, name)
        except AttributeError as e:
            raise AttributeError("'trigger' object has no attribute '%s'" % name)


class BotWrapper:
    def __init__(self, bot):
        self._bot = bot
        self._msg_limit = 10


    def say(self, message):
        if self._msg_limit == 0:
            self._bot.say('[lua] error: message quota exceeded')
        elif self._msg_limit > 0:
            self._bot.say('%s' % message)
        self._msg_limit -= 1
        return self._msg_limit


    def reply(self, message):
        if self._msg_limit == 0:
            self._bot.say('[lua] error: message quota exceeded')
        elif self._msg_limit > 0:
            self._bot.reply('%s' % message)
        self._msg_limit -= 1
        return self._msg_limit


    def __getattr__(self, name):
        try:
            return getattr(self._bot, name)
        except AttributeError as e:
            raise AttributeError("'bot' object has no attribute '%s'" % name)


class Extras:
    def str(self, obj):
        if not isinstance(obj, str):
            return self.dump_json(obj)
        return '%s' % obj


    def load_json(self, obj):
        return json.loads(obj)


    def dump_json(self, obj):
        return json.dumps(obj)


@module.rate(10)
@module.commands('([\S]*)(.*)')
def listen_for_commands(bot, trigger):
    if trigger.sender.is_nick():
        return module.NOLIMIT

    if not trigger.group(2):
        return module.NOLIMIT

    commands = bot.db.get_channel_value(trigger.sender, 'commands')
    if not commands:
        return module.NOLIMIT

    for command, script in commands.items():
        if command == trigger.group(2).lower().strip():
            run_untrusted_lua_script(bot, trigger, script)


@module.commands('def_cmd', 'define_cmd', 'define_command')
@module.require_privilege(module.OP)
@module.require_chanmsg('You must be in a channel to define a command')
def define_cmd(bot, trigger):
    """.define_cmd <name> <lua script> - Create a command based on the given lua script"""
    if not trigger.group(2):
        return bot.say(define_cmd.__doc__)

    commands = bot.db.get_channel_value(trigger.sender, 'commands')
    if not commands:
        commands = dict()

    command = trigger.group(3).lower().strip()
    script = trigger.group(2).replace(command, '', 1).strip()
    commands[command] = script
    bot.db.set_channel_value(trigger.sender, 'commands', commands)
    bot.say("Successfully created new command. You should now be able to run '%s' in %s" % (trigger.group(3), trigger.sender))


@module.commands('get_cmd', 'get_command')
@module.require_privilege(module.OP)
@module.require_chanmsg('You must be in a channel to use this command')
def get_cmd(bot, trigger):
    if not trigger.group(2):
        return bot.say(define_cmd.__doc__)

    commands = bot.db.get_channel_value(trigger.sender, 'commands')
    if not commands:
        commands = dict()

    command = trigger.group(3).lower().strip()
    if command in commands:
        return bot.reply(commands[command])

    bot.reply("'%s' does not exist" % command)


@module.rate(10)
@module.require_privilege(module.VOICE)
@module.commands('lua')
def lua_cmd(bot, trigger):
    script = trigger.group(2)
    run_untrusted_lua_script(bot, trigger, script)


def run_untrusted_lua_script(bot, trigger, script):
    extras = Extras()
    bot = BotWrapper(bot)
    trigger = TriggerWrapper(trigger)

    _allowed_object_attrs = {}
    _allowed_object_attrs[bot] = [
        'say', 
        'reply',
        'db'
    ]
    _allowed_object_attrs[bot.db] = [
        'get_nick_value', 
        'get_channel_value', 
        'get_nick_or_channel_value', 
        'get_preferred_value'
    ]
    _allowed_object_attrs[extras] = ['*']
    _allowed_object_attrs[trigger] = ['*']


    def _attr_getter(obj, attr_name):
        LOGGER.debug('accessing {}.{}'.format(type(obj).__name__, attr_name))
        if isinstance(obj, dict):
            return obj.get(attr_name)

        if not isinstance(attr_name, str):
            raise lupa.LuaError("permission denied %r" % attr_name)

        if isinstance(attr_name, str) and (attr_name.startswith("_") and attr_name != '_G'):
            raise lupa.LuaError("permission denied %r" % attr_name)

        if obj not in _allowed_object_attrs:
            raise lupa.LuaError("permission denied %r" % obj)

        if (attr_name not in _allowed_object_attrs[obj] and 
            '*' not in _allowed_object_attrs[obj]):
            raise lupa.LuaError("permission denied %r" % attr_name)

        value = getattr(obj, attr_name)
        return value

    def _attr_setter(obj, attr_name, value):
        if (attr_name == '_G'):
            return setattr(obj, attr_name, value)
        raise lupa.LuaError('permission denied')

    original_path = os.getcwd()
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox')
    os.chdir(path)
    lua = lupa.LuaRuntime(attribute_handlers=(_attr_getter, _attr_setter))
    setup_lua_paths(lua, None)

    try:
        sandbox_script(lua, script, bot, trigger, extras)
    except Exception as e:
        message = str(e)
        if 'PRE-SANDBOX ERROR: ' in message:
            message = message.partition('PRE-SANDBOX ERROR: ')[2]
        bot.say('[lua] error: ' + message)
    finally:
        os.chdir(original_path)


def sandbox_script(lua, script, bot, trigger, extras):
    sandbox = lua.eval('require("sandbox_test")')
    wrapped = lua.eval("""
function(sandbox, bot, trigger, extras, script) 
  options={env={bot=bot, trigger=trigger, extras=extras}}
  local val = sandbox.protect(script, options)()
  if not (not val or val == '') then
    bot.say(val)
  end
  return val
end""")
    return wrapped(sandbox, bot, trigger, extras, script)


def setup_lua_paths(lua, lua_package_path):
    root = os.path.join(os.path.dirname(__file__), 'lua_modules')
    at_root = lambda *p: os.path.abspath(os.path.join(root, *p))
    default_path = "{root}/?.lua;{libs}/?.lua;{selene}/?.lua".format(
        root=at_root(),
        libs=at_root('libs'),
        selene=at_root('selene')
    )
    if lua_package_path:
        packages_path = ";".join([default_path, lua_package_path])
    else:
        packages_path = default_path

    lua.execute("""
package.path = "{packages_path};" .. package.path
    """.format(packages_path=packages_path))
    lua.execute("""
if not _G._selene then _G._selene = {} end
_G._selene.liveMode = false
_G._selene.doAutoload = true
require("selene")
    """)

